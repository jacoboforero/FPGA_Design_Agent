"""
Implementation agent runtime. Generates RTL via LLM and writes artifacts.
Fails hard if the LLM is unavailable or generation fails.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import List, Tuple

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from core.observability.agentops_tracker import get_tracker
from core.runtime.retry import RetryableError, TaskInputError, is_transient_error


class ImplementationWorker(AgentWorkerBase):
    handled_types = {AgentType.IMPLEMENTATION}
    runtime_name = "agent_implementation"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

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

        if not self.gateway or not Message or not GenerationConfig:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="LLM gateway unavailable; set USE_LLM=1 and configure provider credentials.",
            )
        try:
            rtl_source, log_output = asyncio.run(self._llm_generate_impl(ctx, node_id, iface_signals))
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

        # Sanitize for Verilog-only toolchains.
        lines = []
        for line in rtl_source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("`systemverilog", "```")):
                continue
            lines.append(line)
        rtl_source = "\n".join(lines)
        rtl_source = rtl_source.replace("always_ff", "always")
        rtl_source = rtl_source.replace("always_comb", "always @*")
        if "always" in rtl_source:
            rtl_source = rtl_source.replace("output wire", "output reg")
        rtl_source = rtl_source.replace("logic", "wire")

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
        )

    async def _llm_generate_impl(self, ctx, node_id: str, iface) -> Tuple[str, str]:
        port_lines = []
        for sig in iface:
            dir_kw = sig["direction"].lower()
            name = sig["name"]
            width_expr = self._width_expr(sig)
            width_int = self._width_int(sig)
            if width_int and width_int > 1:
                port_lines.append(f"{dir_kw} logic [{width_int-1}:0] {name}")
            elif width_expr not in ("1", ""):
                port_lines.append(f"{dir_kw} logic [({width_expr})-1:0] {name}")
            else:
                port_lines.append(f"{dir_kw} logic {name}")
        behavior = ctx.get("demo_behavior", "").strip()
        clocking = ctx.get("clocking", {})
        verification = ctx.get("verification", {})
        acceptance = ctx.get("acceptance", {})
        system = (
            "You are an RTL Implementation Agent. Generate synthesizable Verilog-2001.\n"
            "Rules: no code fences, no `systemverilog` directive, avoid SystemVerilog-only keywords (no always_ff/always_comb/logic/interfaces). "
            "If no clock is provided, emit pure combinational logic with continuous assigns only. "
            "If sequential logic is used, declare outputs as reg and drive them in always blocks; no delays inside sequential logic. "
            "Implement the behavior described by the spec summary; do not invent features not stated."
        )
        user = (
            f"Module name: {node_id}\n"
            f"Ports:\n" + "\n".join(f"- {p}" for p in port_lines) + "\n"
            f"Behavior summary:\n{behavior or 'None provided.'}\n"
            f"Clocking:\n{json.dumps(clocking, indent=2)}\n"
            f"Verification hints:\n{json.dumps(verification, indent=2)}\n"
            f"Acceptance:\n{json.dumps(acceptance, indent=2)}\n"
            "Implement the described RTL."
        )
        msgs: List[Message] = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", 600))
        temperature = float(os.getenv("LLM_TEMPERATURE", 0.2))
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens)
        resp = await self.gateway.generate(messages=msgs, config=cfg)  # type: ignore[arg-type]
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
                metadata={"stage": "implementation"},
            )
        except Exception:
            pass
        return resp.content, f"LLM generation via {getattr(resp, 'provider', 'llm')}/{getattr(resp, 'model_name', 'unknown')}"
