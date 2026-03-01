"""
Testbench agent runtime. Generates Verilog-2001 testbenches via LLM.
Fails hard if the LLM is unavailable or generation fails.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import List, Tuple

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from agents.common.tb_sanitizer import sanitize_testbench
from core.observability.agentops_tracker import get_tracker
from core.runtime.retry import RetryableError, TaskInputError, is_transient_error
from core.runtime.config import get_runtime_config


class TestbenchWorker(AgentWorkerBase):
    handled_types = {AgentType.TESTBENCH}
    runtime_name = "agent_testbench"
    __test__ = False

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

        if self._should_use_deterministic_smoke_tb(ctx, node_id):
            tb_source, log_output = self._generate_deterministic_smoke_tb(ctx, node_id)
        else:
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
        # Fix common LLM mistake: $value$plusargs("DUMP") is invalid (it requires a second variable argument).
        # Use $test$plusargs for presence checks, and reserve $value$plusargs for value extraction with a format string.
        tb_source = re.sub(
            r"\$value\$plusargs\s*\(\s*(['\"])DUMP\1\s*\)",
            r"$test$plusargs(\1DUMP\1)",
            tb_source,
        )
        tb_source = re.sub(r"\$stop\s*(\([^;]*\))?\s*;", "$finish;", tb_source)
        if not tb_source.strip().startswith("`timescale"):
            tb_source = "`timescale 1ns/1ps\n\n" + tb_source
        if "endmodule" not in tb_source:
            tb_source = tb_source.rstrip() + "\nendmodule\n"
        tb_source = sanitize_testbench(tb_source)
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

    def _should_use_deterministic_smoke_tb(self, ctx: dict, node_id: str) -> bool:
        top_module = str(ctx.get("top_module") or "").strip()
        if not top_module or top_module == node_id:
            return False
        verification = ctx.get("verification")
        if not isinstance(verification, dict):
            return False
        goals = verification.get("test_goals")
        if not isinstance(goals, list) or not goals:
            return False
        for item in goals:
            text = str(item or "").strip().lower()
            if "smoke" in text:
                return True
        return False

    def _tb_width_decl(self, sig: dict) -> str:
        width_int = self._width_int(sig)
        width_expr = self._width_expr(sig)
        if width_int and width_int > 1:
            return f"[{width_int - 1}:0] "
        if width_expr not in ("1", ""):
            return f"[({width_expr})-1:0] "
        return ""

    def _generate_deterministic_smoke_tb(self, ctx: dict, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        clocking = self._normalize_clocking(ctx.get("clocking"))
        tb_module = f"tb_{node_id}"
        clock_name = clocking["clock_name"]
        reset_name = clocking["reset_name"]
        reset_active_low = bool(clocking["reset_active_expr"].startswith("!"))
        drive_edge = clocking["drive_edge"]

        declared_inputs = {
            str(sig.get("name", "")).strip()
            for sig in iface
            if str(sig.get("direction", "")).upper() == "INPUT"
        }
        has_clock = clock_name in declared_inputs
        has_reset = bool(reset_name) and reset_name in declared_inputs

        lines: list[str] = [f"module {tb_module};", ""]
        lines.extend(
            [
                "integer cycle;",
                "integer dump_enabled;",
                "reg [2047:0] dump_file;",
                "",
            ]
        )

        for sig in iface:
            name = str(sig.get("name", "")).strip()
            direction = str(sig.get("direction", "")).upper()
            width_decl = self._tb_width_decl(sig)
            if direction == "OUTPUT":
                decl = "wire"
            elif direction == "INOUT":
                decl = "wire"
            else:
                decl = "reg"
            lines.append(f"  {decl} {width_decl}{name};")
        lines.append("")

        lines.extend(
            [
                f"  {node_id} dut (",
                "\n".join(
                    f"    .{str(sig.get('name', '')).strip()}({str(sig.get('name', '')).strip()}){',' if idx < len(iface) - 1 else ''}"
                    for idx, sig in enumerate(iface)
                ),
                "  );",
                "",
            ]
        )

        if has_clock:
            lines.extend(
                [
                    f"  initial {clock_name} = 1'b0;",
                    f"  always #5 {clock_name} = ~{clock_name};",
                    "",
                    "  initial cycle = 0;",
                    f"  always @({clocking['sample_edge']} {clock_name}) cycle <= cycle + 1;",
                    "",
                ]
            )

        lines.append("  initial begin")
        for sig in iface:
            name = str(sig.get("name", "")).strip()
            direction = str(sig.get("direction", "")).upper()
            if direction != "INPUT":
                continue
            if has_clock and name == clock_name:
                continue
            if has_reset and name == reset_name:
                continue
            lines.append(f"    {name} = 0;")
        if has_reset:
            active = "1'b0" if reset_active_low else "1'b1"
            inactive = "1'b1" if reset_active_low else "1'b0"
            lines.append(f"    {reset_name} = {active};")
            if has_clock:
                lines.append(f"    repeat (3) @({clocking['sample_edge']} {clock_name});")
            else:
                lines.append("    #30;")
            lines.append(f"    {reset_name} = {inactive};")
        if has_clock:
            lines.append(f"    repeat (2) @({drive_edge} {clock_name});")
            stim_inputs = [
                str(sig.get("name", "")).strip()
                for sig in iface
                if str(sig.get("direction", "")).upper() == "INPUT"
                and str(sig.get("name", "")).strip() not in {clock_name, reset_name}
            ]
            if stim_inputs:
                lines.append(f"    {stim_inputs[0]} = ~{stim_inputs[0]};")
                lines.append(f"    @({drive_edge} {clock_name});")
                lines.append(f"    {stim_inputs[0]} = 0;")
            lines.append(f"    repeat (20) @({clocking['sample_edge']} {clock_name});")
            lines.append('    $display("PASS: cycle=%0d time=%0t smoke test completed", cycle, $time);')
        else:
            lines.append("    #200;")
            lines.append('    $display("PASS: time=%0t smoke test completed", $time);')
        lines.append("    $finish(0);")
        lines.append("  end")
        lines.append("")

        lines.extend(
            [
                "  initial begin",
                '    dump_enabled = $test$plusargs("DUMP");',
                "    if (dump_enabled) begin",
                '      if (!$value$plusargs("DUMP_FILE=%s", dump_file)) dump_file = "dump.vcd";',
                "      $dumpfile(dump_file);",
                f"      $dumpvars(0, {tb_module});",
                "    end",
                "  end",
                "",
                "endmodule",
            ]
        )

        return "\n".join(lines), "Deterministic smoke TB generation for child module."

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

    def _normalize_clocking(self, raw_clocking: object) -> dict:
        # Accept either dict or list[dict] and apply deterministic fallbacks.
        item = {}
        if isinstance(raw_clocking, dict):
            item = raw_clocking
        elif isinstance(raw_clocking, list) and raw_clocking and isinstance(raw_clocking[0], dict):
            item = raw_clocking[0]

        clock_name = str(item.get("clock_name") or "clk")
        clock_polarity = str(item.get("clock_polarity") or "POSEDGE").upper()
        sample_edge = "negedge" if clock_polarity == "NEGEDGE" else "posedge"
        drive_edge = "posedge" if sample_edge == "negedge" else "negedge"

        reset_name_raw = item.get("reset_name")
        reset_name = str(reset_name_raw).strip() if reset_name_raw else "rst_n"
        reset_polarity = str(item.get("reset_polarity") or "ACTIVE_LOW").upper()
        reset_active_low = reset_polarity in {"ACTIVE_LOW", "LOW", "0"}
        reset_active_expr = f"!{reset_name}" if reset_active_low else reset_name

        reset_is_async_raw = item.get("reset_is_async")
        reset_is_async = True if reset_is_async_raw is None else bool(reset_is_async_raw)

        return {
            "clock_name": clock_name,
            "clock_polarity": clock_polarity,
            "sample_edge": sample_edge,
            "drive_edge": drive_edge,
            "reset_name": reset_name,
            "reset_polarity": reset_polarity,
            "reset_is_async": reset_is_async,
            "reset_active_expr": reset_active_expr,
        }

    def _verification_summary(self, verification: dict) -> str:
        if not isinstance(verification, dict):
            return "- No verification plan provided."
        lines: list[str] = []
        goals = verification.get("test_goals")
        if isinstance(goals, list) and goals:
            lines.append("Test goals:")
            lines.extend(f"- {str(goal)}" for goal in goals)
        oracle = verification.get("oracle_strategy")
        if oracle:
            lines.append(f"Oracle strategy: {oracle}")
        stimuli = verification.get("stimulus_strategy")
        if stimuli:
            lines.append(f"Stimulus strategy: {stimuli}")
        pass_fail = verification.get("pass_fail_criteria")
        if isinstance(pass_fail, list) and pass_fail:
            lines.append("Pass/fail criteria:")
            lines.extend(f"- {str(item)}" for item in pass_fail)
        return "\n".join(lines) if lines else "- No verification plan provided."

    async def _llm_generate_tb(self, ctx, node_id: str) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        ports = []
        dut_inputs: list[str] = []
        dut_outputs: list[str] = []
        dut_inouts: list[str] = []
        for sig in iface:
            name = sig["name"]
            width_expr = self._width_expr(sig)
            width_int = self._width_int(sig)
            dir_kw = sig["direction"].lower()
            if dir_kw == "input":
                dut_inputs.append(name)
            elif dir_kw == "output":
                dut_outputs.append(name)
            elif dir_kw == "inout":
                dut_inouts.append(name)
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
        clocking = self._normalize_clocking(ctx.get("clocking"))
        tb_module = f"tb_{node_id}"
        system = (
            "You are a hardware RTL testbench generation agent.\n"
            "Generate one complete self-checking Verilog-2001 testbench.\n\n"
            "Priority order:\n"
            "1) Race-free event ordering.\n"
            "2) Correct checking logic against DUT behavior.\n"
            "3) Verilog-2001 syntax compatibility.\n"
            "4) Readable concise code.\n\n"
            "Output contract:\n"
            "- Output code only. No markdown, no prose, no code fences.\n"
            f"- Module name must be exactly {tb_module}.\n"
            "- Avoid SystemVerilog-only constructs (no logic, always_ff, always_comb, interfaces).\n"
            "- Declare regs/wires/integers at module scope only.\n"
            "- Do not use $stop. Use $finish(1) on failure and $finish(0) on pass.\n"
            "- Failure print must include cycle=<cycle> and time=<time> and key DUT signals.\n\n"
            "Signal-driving contract (strict):\n"
            "- Drive only DUT input ports from the testbench.\n"
            "- DUT output ports are observe-only; never drive them from testbench logic.\n"
            "- Do not assign DUT output nets via continuous assign, procedural assignment, force/release, or task side-effects.\n"
            "- For protocol/reference modeling, use separate ref_* variables instead of driving DUT outputs.\n\n"
            "Hard timing contract (must follow exactly):\n"
            f"- DUT sample edge: {clocking['sample_edge']} {clocking['clock_name']}.\n"
            f"- Drive DUT inputs only on {clocking['drive_edge']} {clocking['clock_name']}. Do not drive stimulus on DUT sample edge.\n"
            f"- Use exactly one clock generator block for {clocking['clock_name']}.\n"
            "- Use one scoreboard block on DUT sample edge.\n"
            "- In that scoreboard block use this order:\n"
            "  (a) handle reset and checker gating,\n"
            "  (b) compute expected_next using blocking assignments from previous expected state and sampled inputs,\n"
            "  (c) wait #1,\n"
            "  (d) compare DUT outputs against expected_next,\n"
            "  (e) commit expected state for next cycle.\n"
            "- Do not split reference-update and compare into separate sample-edge blocks.\n"
            "- Do not rely on multiple #1 delays across multiple always blocks for correctness.\n\n"
            "Reset contract:\n"
            "- Apply reset from time 0.\n"
            f"- Active-reset expression is {clocking['reset_active_expr']}.\n"
            "- Gate checker while reset is active and for at least one sampled edge after reset release.\n\n"
            "Optional dumping:\n"
            "- If +DUMP is present, enable VCD dump.\n"
            "- +DUMP_FILE=<path> via $value$plusargs(\"DUMP_FILE=%s\", ...), default dump.vcd.\n"
            "- Optional +DUMP_START/+DUMP_END window using %d.\n"
            "- Do not treat DUMP_START=0 as disabled."
        )
        user = (
            f"Task:\n"
            f"- DUT module: {node_id}\n"
            f"- Required TB module: {tb_module}\n"
            f"- Port list:\n" + "\n".join(f"  - {p}" for p in ports) + "\n\n"
            f"- DUT input ports (TB may drive): {', '.join(dut_inputs) if dut_inputs else 'none'}\n"
            f"- DUT output ports (observe-only, TB must never drive): {', '.join(dut_outputs) if dut_outputs else 'none'}\n"
            f"- DUT inout ports (avoid driving unless explicitly required): {', '.join(dut_inouts) if dut_inouts else 'none'}\n\n"
            f"Normalized clock/reset contract:\n"
            f"- clock_name: {clocking['clock_name']}\n"
            f"- clock_polarity: {clocking['clock_polarity']}\n"
            f"- sample_edge: {clocking['sample_edge']}\n"
            f"- drive_edge: {clocking['drive_edge']}\n"
            f"- reset_name: {clocking['reset_name']}\n"
            f"- reset_polarity: {clocking['reset_polarity']}\n"
            f"- reset_is_async: {clocking['reset_is_async']}\n"
            f"- reset_active_expr: {clocking['reset_active_expr']}\n\n"
            f"Behavior summary:\n{behavior}\n\n"
            f"Verification summary:\n{self._verification_summary(verification)}\n\n"
            "Generate the full testbench now."
        )
        msgs: List[Message] = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        llm_cfg = get_runtime_config().llm
        max_tokens = int(llm_cfg.max_tokens)
        temperature = float(llm_cfg.temperature)
        top_p = llm_cfg.top_p
        cfg = GenerationConfig(temperature=temperature, top_p=top_p, max_tokens=max_tokens)
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
