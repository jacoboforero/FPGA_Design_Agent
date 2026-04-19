"""
Testbench agent runtime. Generates Verilog-2001 testbenches via LLM.
Fails hard if the LLM is unavailable or generation fails.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, List, Tuple

from adapters.rag.rag_service import retrieve_for_stage
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import apply_reproducibility_settings, init_llm_gateway, Message, MessageRole, GenerationConfig
from agents.common.tb_sanitizer import sanitize_testbench
from core.observability.agentops_tracker import get_tracker
from core.prompting import apply_prompt_output_contract, build_prompt_metadata, render_prompt, write_prompt_trace
from core.runtime.retry import RetryableError, TaskInputError, is_transient_error
from core.runtime.config import get_runtime_config
from core.runtime.paths import task_memory_root
from core.runtime.testbench_contract import extract_reset_semantics, normalize_testbench_contract


def _truncate_prompt_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n... [truncated {omitted} char(s) for prompt efficiency]"


def _testbench_contract_for_context(ctx: dict) -> dict:
    iface = ctx.get("interface") if isinstance(ctx.get("interface"), dict) else {}
    behavior = str(ctx.get("demo_behavior", "") or "").strip()
    return normalize_testbench_contract(
        ctx.get("testbench_contract"),
        interface_signals=iface.get("signals", []),
        raw_clocking=ctx.get("clocking"),
        module_contract=ctx.get("module_contract"),
        reset_semantics=extract_reset_semantics(behavior),
    )


def _format_testbench_contract(contract: dict) -> str:
    lines = [
        f"- mode: {contract.get('mode')}",
        f"- timing_style: {contract.get('timing_style')}",
        f"- checker_style: {contract.get('checker_style')}",
        f"- requires_clock: {contract.get('requires_clock')}",
        f"- clock_name: {contract.get('clock_name')}",
        f"- sample_edge: {contract.get('sample_edge')}",
        f"- drive_edge: {contract.get('drive_edge')}",
        f"- requires_reset: {contract.get('requires_reset')}",
        f"- reset_name: {contract.get('reset_name')}",
        f"- reset_polarity: {contract.get('reset_polarity')}",
        f"- reset_is_async: {contract.get('reset_is_async')}",
        f"- post_reset_settle_cycles: {contract.get('post_reset_settle_cycles')}",
    ]
    return "\n".join(lines)


def _testbench_contract_guidance(contract: dict) -> str:
    mode = str(contract.get("mode") or "").strip().lower()
    if mode == "combinational_no_reset":
        return (
            "Timing contract (must follow exactly):\n"
            "- This DUT is combinational for testbench purposes.\n"
            "- Do not invent clk/clock or rst/reset signals if they are not DUT ports.\n"
            "- Do not create sampled-edge scoreboards, cycle counters, prev_* gating, or post-reset enable logic.\n"
            "- Do not use persistent ref_* scoreboard state across multiple vectors.\n"
            "- Use one simple initial/task-driven stimulus flow; do not add always blocks, while loops, or background polling for check logic.\n"
            "- Apply input vectors from simple initial/task-based stimulus.\n"
            "- For each vector: drive inputs, wait exactly one small settle delay (for example #1), then compare outputs immediately.\n"
            "- Never use more than one delay control between driving a vector and checking that vector.\n"
            "- Compare DUT outputs directly against the combinational expected value.\n"
            "- If an expected value helper is needed, use a one-shot combinational expression or helper function, not a ref_* register that is updated across vectors.\n"
            "- If +DUMP is present, dump the whole run. Do not implement DUMP_START/DUMP_END windows with loops or extra delay chains in combinational benches.\n"
        )
    if mode == "clocked_no_reset":
        return (
            "Timing contract (must follow exactly):\n"
            f"- DUT sample edge: {contract['sample_edge']} {contract['clock_name']}.\n"
            f"- Drive DUT inputs only on {contract['drive_edge']} {contract['clock_name']}. Do not drive stimulus on DUT sample edge.\n"
            f"- Use exactly one clock generator block for {contract['clock_name']}.\n"
            "- Do not invent reset handling or post-reset checker gating.\n"
            "- Use one scoreboard block on DUT sample edge.\n"
            "- In that scoreboard block use this order:\n"
            "  (a) compute expected_next from the current expected state and current sampled DUT inputs,\n"
            "  (b) wait exactly one #1 settle delay so DUT nonblocking updates are visible,\n"
            "  (c) compare DUT outputs against expected_next,\n"
            "  (d) commit expected state for next cycle.\n"
            "- Do not create prev_* shadow copies of sampled controls or expected state for delayed comparisons.\n"
        )
    return (
        "Timing contract (must follow exactly):\n"
        f"- DUT sample edge: {contract['sample_edge']} {contract['clock_name']}.\n"
        f"- Drive DUT inputs only on {contract['drive_edge']} {contract['clock_name']}. Do not drive stimulus on DUT sample edge.\n"
        f"- Use exactly one clock generator block for {contract['clock_name']}.\n"
        "- Use one scoreboard block on DUT sample edge.\n"
        "- In that scoreboard block use this order:\n"
        "  (a) handle reset and checker gating,\n"
        "  (b) compute expected_next using blocking assignments from the current expected state and current sampled inputs,\n"
        "  (c) wait exactly one #1 settle delay so DUT nonblocking updates are visible,\n"
        "  (d) compare DUT outputs against expected_next,\n"
        "  (e) commit expected state for next cycle.\n"
        "- Do not create prev_* shadow copies of sampled controls or expected state for delayed comparisons.\n"
        "- Do not split reference-update and compare into separate sample-edge blocks.\n"
        "- Do not rely on multiple #1 delays across multiple always blocks for correctness.\n"
        "Reset contract:\n"
        "- Apply reset from time 0.\n"
        f"- Active-reset expression is {contract['reset_active_expr']}.\n"
        f"- Gate checker while reset is active and for at least {contract['post_reset_settle_cycles']} sampled edge(s) after reset release.\n"
    )


class TestbenchWorker(AgentWorkerBase):
    handled_types = {AgentType.TESTBENCH}
    runtime_name = "agent_testbench"
    __test__ = False

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway("testbench")

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
                tb_source, log_output, runtime_metadata = asyncio.run(self._llm_generate_tb(ctx, node_id))
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
            runtime_metadata=runtime_metadata if not self._should_use_deterministic_smoke_tb(ctx, node_id) else None,
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
        tb_contract = _testbench_contract_for_context(ctx)
        tb_module = f"tb_{node_id}"
        clock_name = str(tb_contract.get("clock_name") or "clk")
        reset_name = str(tb_contract.get("reset_name") or "")
        reset_active_low = bool(str(tb_contract.get("reset_active_expr") or "").startswith("!"))
        drive_edge = str(tb_contract.get("drive_edge") or "negedge")

        declared_inputs = {
            str(sig.get("name", "")).strip()
            for sig in iface
            if str(sig.get("direction", "")).upper() == "INPUT"
        }
        has_clock = bool(tb_contract.get("requires_clock")) and clock_name in declared_inputs
        has_reset = bool(tb_contract.get("requires_reset")) and bool(reset_name) and reset_name in declared_inputs

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
                    f"  always @({tb_contract['sample_edge']} {clock_name}) cycle <= cycle + 1;",
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
                lines.append(f"    repeat (3) @({tb_contract['sample_edge']} {clock_name});")
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
            lines.append(f"    repeat (20) @({tb_contract['sample_edge']} {clock_name});")
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

    async def _llm_generate_tb(self, ctx, node_id: str) -> Tuple[str, str, dict[str, Any]]:
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
        behavior = _truncate_prompt_text(str(ctx.get("demo_behavior", "")), max_chars=4000)
        verification_summary = _truncate_prompt_text(self._verification_summary(verification), max_chars=4000)
        tb_contract = _testbench_contract_for_context(ctx)
        tb_module = f"tb_{node_id}"
        rag_query = _build_testbench_rag_query(
            node_id=node_id,
            iface=iface,
            behavior=behavior,
            verification=verification,
            tb_contract=tb_contract,
        )
        rag_context, rag_metadata = retrieve_for_stage(
            "testbench",
            rag_query,
            execution_policy=ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else None,
        )
        rag_guidance = ""
        if rag_context.strip():
            rag_guidance = (
                "Relevant prior designs and verification patterns (optional guidance, reuse or adapt when appropriate to the contract and interface):\n"
                f"{rag_context}"
            )
        prompt = render_prompt(
            "testbench.generate",
            {
                "tb_module": tb_module,
                "tb_contract_guidance": _testbench_contract_guidance(tb_contract),
                "rag_guidance": rag_guidance,
                "node_id": node_id,
                "port_lines": "\n".join(f"  - {p}" for p in ports),
                "dut_inputs": ", ".join(dut_inputs) if dut_inputs else "none",
                "dut_outputs": ", ".join(dut_outputs) if dut_outputs else "none",
                "dut_inouts": ", ".join(dut_inouts) if dut_inouts else "none",
                "tb_contract_summary": _format_testbench_contract(tb_contract),
                "behavior": behavior,
                "verification_summary": verification_summary,
            },
        )
        trace_dir = task_memory_root() / node_id / "tb"
        write_prompt_trace(prompt, trace_dir)
        llm_cfg = get_runtime_config().llm
        max_tokens = int(min(llm_cfg.max_tokens, llm_cfg.max_tokens_spec))
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
                    "stage": "testbench",
                    "rag_used": bool(rag_metadata.get("used")),
                    "rag_hit_count": int(rag_metadata.get("hit_count", 0)),
                    **build_prompt_metadata(prompt),
                },
            )
        except Exception:
            pass
        return (
            resp.content,
            f"LLM TB generation via {getattr(resp, 'provider', 'llm')}/{getattr(resp, 'model_name', 'unknown')}",
            {"rag": rag_metadata},
        )


def _build_testbench_rag_query(
    *,
    node_id: str,
    iface: list[dict],
    behavior: str,
    verification: dict[str, Any],
    tb_contract: dict[str, Any],
) -> str:
    port_lines = []
    for signal in iface:
        if not isinstance(signal, dict):
            continue
        port_lines.append(
            f"{signal.get('direction', 'signal')} {signal.get('name', 'unnamed')} width={signal.get('width', 1)}"
        )
    verification_goals = verification.get("test_goals") if isinstance(verification.get("test_goals"), list) else []
    lines = [
        f"testbench query for module {node_id}",
        "interface:",
        *[f"- {item}" for item in port_lines[:24]],
        f"behavior: {behavior or 'none provided'}",
        f"verification_goals: {json.dumps(verification_goals[:8])}",
        f"testbench_contract: {json.dumps(tb_contract, sort_keys=True)}",
    ]
    return "\n".join(lines)
