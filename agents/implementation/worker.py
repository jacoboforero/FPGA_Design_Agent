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

        try:
            if not (self.gateway and Message):
                raise RuntimeError("LLM gateway unavailable; implementation agent requires LLM.")
            iface_signals = ctx["interface"]["signals"]
            rtl_source, log_output = asyncio.run(self._llm_generate_impl(ctx, node_id, iface_signals))
            rtl_source = self._validate_and_clean_rtl(rtl_source, node_id)
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Implementation failed: {exc}",
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

    def _validate_and_clean_rtl(self, rtl_source: str, node_id: str) -> str:
        if not rtl_source or not rtl_source.strip():
            raise RuntimeError("LLM returned empty RTL.")
        cleaned = rtl_source.strip()
        if "module" not in cleaned:
            raise RuntimeError("LLM RTL missing module declaration.")
        if node_id not in cleaned:
            cleaned = cleaned.replace("module ", f"module {node_id} ", 1)
        return cleaned

    async def _llm_generate_impl(self, ctx, node_id: str, iface) -> Tuple[str, str]:
        behavior = ctx.get("demo_behavior", "")
        clocking = ctx.get("clocking", {})
        clock_name = next(iter(clocking.keys()), None) if isinstance(clocking, dict) else None
        port_lines = []
        for sig in iface:
            dir_kw = sig["direction"].lower()
            name = sig["name"]
            width = sig.get("width", 1)
            port_lines.append(f"{dir_kw} logic [{width-1}:0] {name}" if width > 1 else f"{dir_kw} logic {name}")
        system = (
            "You are an RTL Implementation Agent. Generate synthesizable Verilog-2001.\n"
            "Rules: no code fences, no `systemverilog` directive, avoid SystemVerilog-only keywords (no always_ff/always_comb/logic/interfaces). "
            "If no clock is provided, emit pure combinational logic with continuous assigns only. "
            "If sequential logic is used, declare outputs as reg and drive them in always blocks; no delays inside sequential logic. "
            "Honor any ready/valid or reset semantics described. Output ONLY code."
        )
        user = (
            f"Module name: {node_id}\n"
            f"Ports:\n" + "\n".join(f"- {p}" for p in port_lines) + "\n"
            f"Behavior summary: {behavior or 'Implement basic ready/valid passthrough'}\n"
            f"Clock: {clock_name or 'none'}\n"
            "Implement the described behavior faithfully and include reset handling if a reset signal exists."
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
