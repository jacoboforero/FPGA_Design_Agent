"""
Implementation agent runtime. Generates RTL via LLM and writes artifacts.
Fails hard if the LLM is unavailable or generation fails.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, List, Tuple

from adapters.rag.rag_service import retrieve_for_stage
from agents.common.rag_queries import build_implementation_rag_query
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import apply_reproducibility_settings, init_llm_gateway, Message, MessageRole, GenerationConfig
from core.observability.agentops_tracker import get_tracker
from core.prompting import (
    PromptRegistry,
    apply_prompt_output_contract,
    build_prompt_metadata,
    render_prompt,
    write_prompt_trace,
)
from core.runtime.retry import RetryableError, TaskInputError, is_transient_error
from core.runtime.config import get_runtime_config
from core.runtime.paths import task_memory_root

_NO_FENCE_PREFIXES = ("`systemverilog", "```")
_ALWAYS_FF_RE = re.compile(r"\balways_ff\b")
_ALWAYS_COMB_RE = re.compile(r"\balways_comb\b")
_OUTPUT_LOGIC_RE = re.compile(r"\boutput\s+logic\b")
_LOGIC_RE = re.compile(r"\blogic\b")
_PROMPT_REGISTRY = PromptRegistry()


class ImplementationWorker(AgentWorkerBase):
    handled_types = {AgentType.IMPLEMENTATION}
    runtime_name = "agent_implementation"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway("implementation")

    def _width_expr(self, sig) -> str:
        raw = sig.get("width", 1)
        if isinstance(raw, bool):
            return "1"
        if isinstance(raw, (int, float)):
            return str(int(raw))
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return "1"

    def _width_int(self, sig) -> int | None:
        raw = sig.get("width", 1)
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
        if isinstance(raw, str):
            text = raw.strip()
            if text.isdigit():
                return int(text)
        return None

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        if "rtl_path" not in ctx:
            raise TaskInputError("Missing rtl_path in task context.")
        if not isinstance(ctx.get("interface"), dict) or "signals" not in ctx["interface"]:
            raise TaskInputError("Missing interface signals in task context.")
        if "node_id" not in ctx:
            raise TaskInputError("Missing node_id in task context.")
        node_id = ctx["node_id"]
        rtl_path = Path(ctx["rtl_path"])
        rtl_path.parent.mkdir(parents=True, exist_ok=True)

        iface_signals = ctx["interface"]["signals"]
        if not isinstance(iface_signals, list) or not iface_signals:
            raise TaskInputError("Empty interface signals in task context.")

        integration_error = self._validate_integration_context(ctx)
        if integration_error:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=integration_error,
            )

        if not self.gateway or not Message or not GenerationConfig:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="LLM gateway unavailable; set USE_LLM=1 and configure provider credentials.",
            )
        try:
            rtl_source, log_output, runtime_metadata = asyncio.run(
                self._llm_generate_impl(ctx, node_id, iface_signals)
            )
        except Exception as exc:  # noqa: BLE001
            if is_transient_error(exc):
                raise RetryableError(f"LLM generation transient error: {exc}")
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"LLM generation failed: {exc}",
            )
        if not rtl_source or not rtl_source.strip():
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="LLM returned empty RTL source.",
            )

        rtl_language = _rtl_language_for_context(ctx)
        rtl_source = _sanitize_rtl_source(rtl_source, rtl_language=rtl_language)
        rtl_source = _extract_target_module_source(rtl_source, node_id)

        try:
            rtl_path.write_text(rtl_source)
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Failed to write RTL to {rtl_path}: {exc}",
            )
        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "artifacts_path": str(rtl_path)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(rtl_path),
            log_output=log_output,
            runtime_metadata=runtime_metadata,
        )

    def _validate_integration_context(self, ctx: dict) -> str | None:
        children = ctx.get("children") or []
        if not isinstance(children, list):
            return "Integration context error: 'children' must be a list."
        children = [str(child).strip() for child in children if str(child).strip()]
        if not children:
            return None

        child_interfaces = ctx.get("child_interfaces")
        if not isinstance(child_interfaces, dict):
            return (
                "Integration context error: missing child_interfaces for module with children. "
                "Provide per-child L2 interface signals in design context."
            )

        connections = ctx.get("connections")
        if not isinstance(connections, list) or not connections:
            return (
                "Integration context error: missing L4.connections for module with children. "
                "Define explicit connection endpoints for child integration."
            )

        child_ports: dict[str, set[str]] = {}
        for child in children:
            iface = child_interfaces.get(child)
            if not isinstance(iface, dict):
                return (
                    f"Integration context error: missing interface for child '{child}'. "
                    "Define the child Module section with explicit L2.signals."
                )
            signals = iface.get("signals")
            if not isinstance(signals, list) or not signals:
                return (
                    f"Integration context error: child '{child}' has no interface signals. "
                    "Define explicit L2.signals for this child module."
                )
            ports = {
                str(sig.get("name", "")).strip()
                for sig in signals
                if isinstance(sig, dict) and str(sig.get("name", "")).strip()
            }
            if not ports:
                return (
                    f"Integration context error: child '{child}' has no named interface ports. "
                    "Define valid L2.signals names for this child module."
                )
            child_ports[child] = ports

        connected_children: set[str] = set()
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            for side_name in ("src", "dst"):
                endpoint = conn.get(side_name)
                if not isinstance(endpoint, dict):
                    continue
                node_id = str(endpoint.get("node_id", "")).strip()
                port = str(endpoint.get("port", "")).strip()
                if not node_id or not port:
                    continue
                if node_id not in child_ports:
                    continue
                if port not in child_ports[node_id]:
                    allowed = ", ".join(sorted(child_ports[node_id]))
                    return (
                        f"Integration context error: connection endpoint '{node_id}.{port}' is not declared in child "
                        f"interface. Allowed child ports: [{allowed}]"
                    )
                connected_children.add(node_id)

        missing_connections = [child for child in children if child not in connected_children]
        if missing_connections:
            missing = ", ".join(missing_connections)
            return (
                "Integration context error: no L4.connections endpoint found for child module(s): "
                f"{missing}. Add explicit child wiring before RTL generation."
            )

        return None

    async def _llm_generate_impl(self, ctx, node_id: str, iface) -> Tuple[str, str, dict[str, Any]]:
        rtl_language = _rtl_language_for_context(ctx)
        port_lines = []
        for sig in iface:
            port_lines.append(self._prompt_port_line(sig, rtl_language=rtl_language))
        behavior, behavior_label = _behavior_prompt_for_context(ctx)
        clocking = ctx.get("clocking", {})
        verification = ctx.get("verification", {})
        acceptance = ctx.get("acceptance", {})
        children = ctx.get("children") or []
        child_interfaces = ctx.get("child_interfaces") or {}
        connections = ctx.get("connections") or []
        module_contract = ctx.get("module_contract") or {}
        contract_style = str(module_contract.get("style", "")).strip().lower()
        rag_query = build_implementation_rag_query(
            node_id=node_id,
            iface=iface,
            behavior=behavior,
            verification=verification,
            module_contract=module_contract,
            children=children,
            child_interfaces=child_interfaces,
            connections=connections,
        )
        rag_context, rag_metadata = retrieve_for_stage(
            "implementation",
            rag_query,
            execution_policy=ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else None,
        )
        rtl_language_rules = _PROMPT_REGISTRY.render_fragment(
            f"implementation/rtl_language/{'systemverilog' if rtl_language == 'systemverilog' else 'verilog2001'}.md"
        )
        contract_parts: list[str] = []
        if contract_style == "combinational":
            contract_parts.append(
                _PROMPT_REGISTRY.render_fragment(
                    "implementation/contract/combinational.md",
                    {
                        "always_keyword": "always_comb" if rtl_language == "systemverilog" else "always @*",
                    },
                )
            )
        if contract_style == "integration" and bool(module_contract.get("prefer_debug_passthrough")):
            contract_parts.append(
                _PROMPT_REGISTRY.render_fragment("implementation/contract/integration_debug_passthrough.md")
            )
        integration_rules = (
            _PROMPT_REGISTRY.render_fragment("implementation/integration_rules.md")
            if children
            else ""
        )
        rag_guidance = ""
        if rag_context.strip():
            rag_guidance = (
                "Relevant prior designs (optional guidance, reuse or adapt when appropriate to the contract and interface):\n"
                f"{rag_context}"
            )
        prompt = render_prompt(
            "implementation.generate",
            {
                "rtl_language_rules": rtl_language_rules,
                "contract_rules": "\n".join(contract_parts),
                "integration_rules": integration_rules,
                "rag_guidance": rag_guidance,
                "node_id": node_id,
                "port_lines": "\n".join(f"- {p}" for p in port_lines),
                "behavior_label": behavior_label,
                "behavior": behavior or "None provided.",
                "clocking_json": json.dumps(clocking, indent=2),
                "verification_json": json.dumps(verification, indent=2),
                "acceptance_json": json.dumps(acceptance, indent=2),
                "module_contract_json": json.dumps(module_contract, indent=2),
                "children_json": json.dumps(children, indent=2),
                "child_interfaces_json": json.dumps(child_interfaces, indent=2),
                "connections_json": json.dumps(connections, indent=2),
            },
        )
        trace_dir = task_memory_root() / node_id / "impl"
        write_prompt_trace(prompt, trace_dir)
        llm_cfg = get_runtime_config().llm
        max_tokens = int(llm_cfg.max_tokens)
        temperature = float(llm_cfg.temperature)
        top_p = llm_cfg.top_p
        cfg = GenerationConfig(temperature=temperature, top_p=top_p, max_tokens=max_tokens)
        cfg = apply_reproducibility_settings(cfg, provider=getattr(self.gateway, "provider", None))
        cfg = apply_prompt_output_contract(cfg, prompt)
        resp = await self.gateway.generate(messages=prompt.messages, config=cfg)  # type: ignore[arg-type]
        tracker = get_tracker()
        try:
            tracker.log_llm_call(
                agent=self.runtime_name,
                node_id=node_id,
                model=getattr(resp, "model_name", "unknown"),
                provider=getattr(resp, "provider", "unknown"),
                prompt_tokens=getattr(resp, "input_tokens", 0),
                completion_tokens=getattr(resp, "output_tokens", 0),
                total_tokens=getattr(resp, "total_tokens", 0),
                estimated_cost_usd=getattr(resp, "estimated_cost_usd", None),
                metadata={
                    "stage": "implementation",
                    "rag_used": bool(rag_metadata.get("used")),
                    "rag_hit_count": int(rag_metadata.get("hit_count", 0)),
                    **build_prompt_metadata(prompt),
                },
            )
        except Exception:
            pass
        return (
            resp.content,
            f"LLM generation via {getattr(resp, 'provider', 'llm')}/{getattr(resp, 'model_name', 'unknown')}",
            {"rag": rag_metadata},
        )

    def _prompt_port_line(self, sig: dict, *, rtl_language: str) -> str:
        dir_kw = str(sig["direction"]).lower()
        name = str(sig["name"])
        width_expr = self._width_expr(sig)
        width_int = self._width_int(sig)
        if width_int and width_int > 1:
            width_text = f"[{width_int-1}:0] "
        elif width_expr not in ("1", ""):
            width_text = f"[({width_expr})-1:0] "
        else:
            width_text = ""
        if rtl_language == "systemverilog":
            return f"{dir_kw} logic {width_text}{name}".replace("  ", " ").strip()
        return f"{dir_kw} {width_text}{name}".replace("  ", " ").strip()


_MODULE_DECL_RE = re.compile(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_ENDMODULE_RE = re.compile(r"^\s*endmodule\b")


def _sanitize_rtl_source(source: str, *, rtl_language: str) -> str:
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(_NO_FENCE_PREFIXES):
            continue
        lines.append(line)
    text = "\n".join(lines)
    if rtl_language == "systemverilog":
        return text
    text = _ALWAYS_FF_RE.sub("always", text)
    text = _ALWAYS_COMB_RE.sub("always @*", text)
    if "always" in text:
        text = _OUTPUT_LOGIC_RE.sub("output reg", text)
    text = _LOGIC_RE.sub("wire", text)
    return text


def _rtl_language_for_context(ctx: dict) -> str:
    execution_policy = ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else {}
    language = str(execution_policy.get("rtl_language", "verilog2001")).strip().lower()
    if language == "systemverilog":
        return "systemverilog"
    return "verilog2001"


def _behavior_prompt_for_context(ctx: dict) -> tuple[str, str]:
    execution_policy = ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else {}
    prompt_mode = str(execution_policy.get("benchmark_prompt_mode", "normalized")).strip().lower()
    benchmark_prompt = str(ctx.get("benchmark_prompt", "") or "").strip()
    if prompt_mode == "raw_verilog_eval" and benchmark_prompt:
        return benchmark_prompt, "Benchmark prompt (verbatim)"
    return str(ctx.get("demo_behavior", "") or "").strip(), "Behavior summary"


def _extract_target_module_source(source: str, module_name: str) -> str:
    lines = source.splitlines()
    blocks: list[tuple[str, int, int]] = []
    in_module = False
    start_idx = -1
    current_name = ""

    for idx, line in enumerate(lines):
        if not in_module:
            match = _MODULE_DECL_RE.match(line)
            if match:
                in_module = True
                current_name = match.group(1)
                start_idx = idx
            continue
        if _ENDMODULE_RE.match(line):
            blocks.append((current_name, start_idx, idx))
            in_module = False
            start_idx = -1
            current_name = ""

    if len(blocks) <= 1:
        return source

    chosen = next((item for item in blocks if item[0] == module_name), None)
    if not chosen:
        return source
    _, start, end = chosen
    selected = "\n".join(lines[start : end + 1]).strip()

    timescale_line = next((line.strip() for line in lines if line.strip().startswith("`timescale")), "")
    if timescale_line and not selected.startswith("`timescale"):
        selected = f"{timescale_line}\n\n{selected}"
    return selected.rstrip() + "\n"
