"""
Implementation agent runtime. Generates RTL (LLM-backed when enabled, otherwise
fallback stub) and writes artifacts to the provided path.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import List, Tuple

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from core.observability.agentops_tracker import get_tracker


class ImplementationWorker(AgentWorkerBase):
    handled_types = {AgentType.IMPLEMENTATION}
    runtime_name = "agent_implementation"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        node_id = ctx["node_id"]
        rtl_path = Path(ctx["rtl_path"])
        rtl_path.parent.mkdir(parents=True, exist_ok=True)

        iface_signals = ctx["interface"]["signals"]

        def _width_expr(sig) -> str:
            raw = sig.get("width", 1)
            if isinstance(raw, bool):
                return "1"
            if isinstance(raw, (int, float)):
                return str(int(raw))
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
            return "1"

        def _width_int(sig) -> int | None:
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

        def _port_decl(sig) -> str:
            dir_kw = sig["direction"].lower()
            name = sig["name"]
            width_expr = _width_expr(sig)
            width_int = _width_int(sig)
            if width_int and width_int > 1:
                return f"{dir_kw} wire [{width_int-1}:0] {name}"
            if width_expr not in ("1", ""):
                return f"{dir_kw} wire [({width_expr})-1:0] {name}"
            return f"{dir_kw} wire {name}"

        # Heuristics for deterministic fallbacks to avoid fragile LLM output.
        inputs = [s for s in iface_signals if s["direction"].lower() == "input"]
        outputs = [s for s in iface_signals if s["direction"].lower() == "output"]
        has_clock = any("clk" in s["name"].lower() for s in inputs)
        has_en = any(s["name"].lower() in ("en", "enable") for s in inputs)
        count_out = next((s for s in outputs if "count" in s["name"].lower()), None)

        if has_clock and has_en and count_out:
            # Deterministic up-counter stub.
            clk_name = next(s["name"] for s in inputs if "clk" in s["name"].lower())
            rst = next((s for s in inputs if "rst" in s["name"].lower()), None)
            en = next((s for s in inputs if s["name"].lower() in ("en", "enable")), None)
            width_expr = _width_expr(count_out)
            width_int = _width_int(count_out) or 1
            width_lit = width_expr if width_expr else str(width_int)
            rst_cond = f"!{rst['name']}" if rst else "1'b0"
            ports = [
                _port_decl(sig)
                for sig in iface_signals
            ]
            port_block = ",\n    ".join(ports)
            rtl_source = f"""module {node_id} (
    {port_block}
);
    always @(posedge {clk_name} or negedge {rst['name'] if rst else clk_name}) begin
        if ({rst_cond})
            {count_out['name']} <= {width_lit}'d0;
        else if ({en['name']})
            {count_out['name']} <= {count_out['name']} + {width_lit}'d1;
    end
endmodule
"""
            log_output = "Deterministic up-counter stub emitted (clock/en/count detected)."
        else:
            if self.gateway and Message:
                rtl_source, log_output = asyncio.run(self._llm_generate_impl(ctx, node_id, iface_signals))
            else:
                rtl_source, log_output = self._fallback_generate_impl(ctx, node_id)

            if not has_clock:
                # Force a deterministic combinational stub for pure combinational modules.
                if inputs and outputs:
                    comb_expr = " & ".join(inp["name"] for inp in inputs)
                    assigns = [f"assign {out['name']} = {comb_expr};" for out in outputs]
                    ports = [
                        _port_decl(sig)
                        for sig in iface_signals
                    ]
                    port_block = ",\n    ".join(ports)
                    rtl_source = f"""module {node_id} (
    {port_block}
);
\n  {' '.join(assigns)}\n\nendmodule
"""
                    log_output = f"{log_output} (LLM output replaced with deterministic combinational stub)"

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

        rtl_path.write_text(rtl_source)
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
            width_expr = _width_expr(sig)
            width_int = _width_int(sig)
            if width_int and width_int > 1:
                port_lines.append(f"{dir_kw} logic [{width_int-1}:0] {name}")
            elif width_expr not in ("1", ""):
                port_lines.append(f"{dir_kw} logic [({width_expr})-1:0] {name}")
            else:
                port_lines.append(f"{dir_kw} logic {name}")
        system = (
            "You are an RTL Implementation Agent. Generate synthesizable Verilog-2001.\n"
            "Rules: no code fences, no `systemverilog` directive, avoid SystemVerilog-only keywords (no always_ff/always_comb/logic/interfaces). "
            "If no clock is provided, emit pure combinational logic with continuous assigns only. "
            "If sequential logic is used, declare outputs as reg and drive them in always blocks; no delays inside sequential logic. Output ONLY code."
        )
        user = (
            f"Module name: {node_id}\n"
            f"Ports:\n" + "\n".join(f"- {p}" for p in port_lines) + "\n"
            "Implement a simple passthrough/placeholder consistent with interface."
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

    def _fallback_generate_impl(self, ctx, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        ports = []
        assigns = []
        inputs = [s for s in iface if s["direction"].lower() == "input"]
        for sig in iface:
            dir_kw = sig["direction"].lower()
            name = sig["name"]
            width_expr = _width_expr(sig)
            width_int = _width_int(sig)
            if width_int and width_int > 1:
                ports.append(f"{dir_kw} wire [{width_int-1}:0] {name}")
            elif width_expr not in ("1", ""):
                ports.append(f"{dir_kw} wire [({width_expr})-1:0] {name}")
            else:
                ports.append(f"{dir_kw} wire {name}")
            if dir_kw == "output":
                src = inputs[0] if inputs else None
                if src and _width_expr(src) == width_expr:
                    assigns.append(f"  assign {name} = {src['name']};")
                else:
                    default_val = f"{width_expr}'d0" if width_expr not in ("1", "") else "1'b0"
                    assigns.append(f"  assign {name} = {default_val};")
        port_block = ",\n    ".join(ports)
        assign_block = "\n".join(assigns) if assigns else "  // passthrough stub"
        rtl = f"""module {node_id} (
    {port_block}
);

{assign_block}

endmodule
"""
        return rtl, "Fallback RTL generation (wire-based passthrough stub)."
