"""
Testbench agent runtime. Generates SystemVerilog TBs (LLM-backed when enabled,
fallback stub otherwise).
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


class TestbenchWorker(AgentWorkerBase):
    handled_types = {AgentType.TESTBENCH}
    runtime_name = "agent_testbench"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        node_id = ctx["node_id"]
        tb_path = Path(ctx.get("tb_path", "")) if ctx.get("tb_path") else Path(ctx["rtl_path"]).with_name(f"{node_id}_tb.sv")
        tb_path.parent.mkdir(parents=True, exist_ok=True)

        if self.gateway and Message:
            tb_source, log_output = asyncio.run(self._llm_generate_tb(ctx, node_id))
            tb_source = tb_source.replace("logic", "reg")
            use_raw = os.getenv("TB_USE_LLM_RAW", "0") == "1"
            if not use_raw:
                # Prefer deterministic stub for tool compatibility; keep note of LLM call.
                fallback_src, _ = self._fallback_generate_tb(ctx, node_id)
                tb_source = fallback_src
                log_output = f"{log_output} (LLM output discarded for sim compatibility; set TB_USE_LLM_RAW=1 to keep)"
        else:
            tb_source, log_output = self._fallback_generate_tb(ctx, node_id)

        # Strip unsupported directives that occasionally show up in LLM output.
        tb_source = "\n".join(
            line for line in tb_source.splitlines() if not line.strip().startswith(("`systemverilog", "```"))
        )
        if not tb_source.strip().startswith("`timescale"):
            tb_source = "`timescale 1ns/1ps\n\n" + tb_source
        if "endmodule" not in tb_source:
            tb_source = tb_source.rstrip() + "\nendmodule\n"
        tb_path.write_text(tb_source)
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

    async def _llm_generate_tb(self, ctx, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        ports = []
        for sig in iface:
            name = sig["name"]
            width = sig.get("width", 1)
            dir_kw = sig["direction"].lower()
            base_type = "wire" if dir_kw == "output" else "reg"
            width_decl = f"[{width-1}:0] " if width > 1 else ""
            ports.append(f"{dir_kw} {base_type} {width_decl}{name}")
        system = (
            "You are a Verification Agent. Generate a simple self-checking Verilog-2001 testbench.\n"
            "No code fences, no `systemverilog` directive, avoid SystemVerilog-only keywords (no logic/always_ff/always_comb/interfaces). "
            "Use regs for driven signals, wires for DUT outputs. Keep it concise."
        )
        user = (
            f"Unit Under Test: {node_id}\n"
            f"Ports:\n" + "\n".join(f"- {p}" for p in ports) + "\n"
            "Test basic stimulus to toggle inputs and observe outputs."
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

    def _fallback_generate_tb(self, ctx, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        inputs = [s for s in iface if s["direction"].lower() == "input"]
        outputs = [s for s in iface if s["direction"].lower() == "output"]

        def port_decl(sig):
            width = sig.get("width", 1)
            decl_type = "wire" if sig["direction"].lower() == "output" else "reg"
            return f"{decl_type} [{width-1}:0] {sig['name']}" if width > 1 else f"{decl_type} {sig['name']}"

        port_lines = "\n  ".join(port_decl(s) + ";" for s in iface)

        init_block = "\n    ".join(f"{inp['name']} = '0;" for inp in inputs) if inputs else "// no inputs to drive"
        observe = "\n    ".join(f'$display("Observed {out["name"]}=%h", {out["name"]});' for out in outputs) if outputs else "// no outputs to observe"

        drive_block = "// no stimulus"
        if inputs and all(inp.get("width", 1) == 1 for inp in inputs) and len(inputs) <= 4:
            drive_block = "repeat (16) begin\n      {"
            drive_block += ", ".join(inp["name"] for inp in inputs)
            drive_block += "} = $random;\n      #5;\n    end"
        elif inputs:
            first = inputs[0]
            val = "1'b1" if first.get("width", 1) == 1 else f"{first.get('width',1)}'hA"
            drive_block = f"{first['name']} = {val};"
        tb = f"""`timescale 1ns/1ps

module {node_id}_tb;
  {port_lines}

  {node_id} dut (
    {", ".join(f".{s['name']}({s['name']})" for s in iface)}
  );

  initial begin
    $display("Running stub TB for {node_id}");
    {init_block}
    #5;
    {drive_block}
    #5;
    {observe}
    #5;
    $finish;
  end
endmodule
"""
        return tb, "Fallback TB generation (reg/wire smoke test)."
