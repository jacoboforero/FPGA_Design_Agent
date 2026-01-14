"""
Testbench agent runtime. Generates SystemVerilog TBs via LLM.
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


class TestbenchWorker(AgentWorkerBase):
    handled_types = {AgentType.TESTBENCH}
    runtime_name = "agent_testbench"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        if "node_id" not in ctx:
            raise TaskInputError("Missing node_id in task context.")
        if "rtl_path" not in ctx:
            raise TaskInputError("Missing rtl_path in task context.")
        if not isinstance(ctx.get("interface"), dict) or "signals" not in ctx["interface"]:
            raise TaskInputError("Missing interface signals in task context.")
        node_id = ctx["node_id"]
        iface_signals = ctx["interface"]["signals"]
        if not isinstance(iface_signals, list) or not iface_signals:
            raise TaskInputError("Empty interface signals in task context.")
        tb_path = Path(ctx.get("tb_path", "")) if ctx.get("tb_path") else Path(ctx["rtl_path"]).with_name(f"{node_id}_tb.sv")
        tb_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.gateway or not Message or not GenerationConfig:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="LLM gateway unavailable; set USE_LLM=1 and configure provider credentials.",
            )
        try:
            tb_source, log_output = asyncio.run(self._llm_generate_tb(ctx, node_id))
        except Exception as exc:  # noqa: BLE001
            if is_transient_error(exc):
                raise RetryableError(f"LLM testbench transient error: {exc}")
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"LLM testbench generation failed: {exc}",
            )
        if not tb_source or not tb_source.strip():
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="LLM returned empty testbench source.",
            )
        tb_source = tb_source.replace("logic", "reg")

        # Strip unsupported directives that occasionally show up in LLM output.
        tb_source = "\n".join(
            line for line in tb_source.splitlines() if not line.strip().startswith(("`systemverilog", "```"))
        )
        if not tb_source.strip().startswith("`timescale"):
            tb_source = "`timescale 1ns/1ps\n\n" + tb_source
        if "endmodule" not in tb_source:
            tb_source = tb_source.rstrip() + "\nendmodule\n"
        try:
            tb_path.write_text(tb_source)
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Failed to write testbench to {tb_path}: {exc}",
            )
        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "artifacts_path": str(tb_path)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(tb_path),
            log_output=log_output,
        )

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

    async def _llm_generate_tb(self, ctx, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        ports = []
        for sig in iface:
            name = sig["name"]
            width_expr = self._width_expr(sig)
            width_int = self._width_int(sig)
            dir_kw = sig["direction"].lower()
            base_type = "wire" if dir_kw == "output" else "reg"
            if width_int and width_int > 1:
                width_decl = f"[{width_int-1}:0] "
            elif width_expr not in ("1", ""):
                width_decl = f"[({width_expr})-1:0] "
            else:
                width_decl = ""
            ports.append(f"{dir_kw} {base_type} {width_decl}{name}")
        verification = ctx.get("verification", {})
        behavior = ctx.get("demo_behavior", "")
        clocking = ctx.get("clocking", {})
        system = (
            "You are a Verification Agent. Generate a simple self-checking Verilog-2001 testbench.\n"
            "No code fences, no `systemverilog` directive, avoid SystemVerilog-only keywords (no logic/always_ff/always_comb/interfaces). "
            "Use regs for driven signals, wires for DUT outputs. Keep it concise and target the stated test goals."
        )
        user = (
            f"Unit Under Test: {node_id}\n"
            f"Ports:\n" + "\n".join(f"- {p}" for p in ports) + "\n"
            f"Behavior summary:\n{behavior}\n"
            f"Clocking:\n{json.dumps(clocking, indent=2)}\n"
            f"Verification plan:\n{json.dumps(verification, indent=2)}\n"
            "Create a testbench that exercises the listed goals and checks outputs."
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
                metadata={"stage": "testbench"},
            )
        except Exception:
            pass
        return resp.content, f"LLM TB generation via {getattr(resp, 'provider', 'llm')}/{getattr(resp, 'model_name', 'unknown')}"
