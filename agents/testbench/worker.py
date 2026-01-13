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

        try:
            if not (self.gateway and Message):
                raise RuntimeError("LLM gateway unavailable; testbench agent requires LLM.")
            attempts = 2
            compile_error = None
            last_log = ""
            for attempt in range(attempts):
                tb_source, log_output = asyncio.run(self._llm_generate_tb(ctx, node_id, compile_error=compile_error))
                tb_source = tb_source.replace("logic", "reg")
                last_log = log_output

                # Normalize termination and strip unsupported directives.
                if "$stop" in tb_source:
                    tb_source = tb_source.replace("$stop", "$finish")
                if "$finish" not in tb_source:
                    tb_source += "\ninitial begin\n  #1000;\n  $finish;\nend\n"
                tb_source = "\n".join(
                    line for line in tb_source.splitlines() if not line.strip().startswith(("`systemverilog", "```"))
                )
                if not tb_source.strip().startswith("`timescale"):
                    tb_source = "`timescale 1ns/1ps\n\n" + tb_source
                if "endmodule" not in tb_source:
                    tb_source = tb_source.rstrip() + "\nendmodule\n"
                tb_source = self._hoist_declarations(tb_source)
                tb_source = self._balance_blocks(tb_source)
                self._validate_tb(tb_source, node_id)

                tb_path.write_text(tb_source)

                # Quick syntax check with iverilog if available; if it fails, feed error back to LLM for a retry.
                compile_error = self._syntax_check(ctx.get("rtl_path"), str(tb_path))
                if not compile_error:
                    break
                last_log += f"\nRetrying after compile error:\n{compile_error}"

            if compile_error:
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=str(tb_path),
                    log_output=last_log + "\nFinal compile error:\n" + compile_error,
                )
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Testbench generation failed: {exc}",
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
            log_output=last_log,
        )

    async def _llm_generate_tb(self, ctx, node_id: str, compile_error: str | None = None) -> Tuple[str, str]:
        iface = ctx["interface"]["signals"]
        behavior = ctx.get("demo_behavior", "")
        coverage_goals = ctx.get("coverage_goals", {})
        test_plan = ctx.get("test_plan", [])
        clocking = ctx.get("clocking", {})
        clock_name = next(iter(clocking.keys()), None) if isinstance(clocking, dict) else None
        clock_freq = None
        if clock_name and isinstance(clocking.get(clock_name), dict):
            clock_freq = clocking[clock_name].get("freq_hz")
        ports = []
        for sig in iface:
            name = sig["name"]
            width = sig.get("width", 1)
            dir_kw = sig["direction"].lower()
            base_type = "wire" if dir_kw == "output" else "reg"
            width_decl = f"[{width-1}:0] " if width > 1 else ""
            ports.append(f"{dir_kw} {base_type} {width_decl}{name}")
        system = (
            "You are a Verification Agent. Generate a concise, self-checking Verilog-2001 testbench that terminates cleanly.\n"
            "Rules: no code fences, no `systemverilog` directive, avoid SystemVerilog-only keywords (no logic/always_ff/always_comb/interfaces). "
            "Use regs for driven signals, wires for DUT outputs. Drive reset/clock if present. Include a timeout + $finish (never use $stop). "
            "Declare all regs/wires/integers at module scope (no declarations inside initial/always blocks). "
            "Check basic ready/valid or handshake semantics from the behavior summary."
        )
        clock_note = ""
        if clock_name and clock_freq:
            try:
                period_ns = max(1, int(1e9 / float(clock_freq)))
                clock_note = f"Use clock '{clock_name}' with period ~{period_ns}ns."
            except Exception:
                clock_note = f"Use clock '{clock_name}' with a reasonable period."
        test_expectations = ""
        if test_plan:
            test_expectations = "Test goals:\n" + "\n".join(f"- {t}" for t in test_plan)
        if coverage_goals and not test_expectations:
            test_expectations = "Coverage hints:\n" + "\n".join(f"- {k}: {v}" for k, v in coverage_goals.items())
        compile_hint = f"Previous compile error:\n{compile_error}\nPlease fix the syntax while keeping the test intent." if compile_error else ""
        user = (
            f"Unit Under Test: {node_id}\n"
            f"Ports:\n" + "\n".join(f"- {p}" for p in ports) + "\n"
            f"Behavior summary: {behavior}\n"
            f"{test_expectations}\n"
            f"{clock_note}\n"
            "Ensure the TB finishes with $finish after exercising reset and a few stimulus phases."
            f"\n{compile_hint}"
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

    def _syntax_check(self, rtl_path: str | None, tb_path: str) -> str | None:
        import shutil
        import subprocess
        iverilog = shutil.which("iverilog")
        if not iverilog or not rtl_path:
            return None
        out_bin = "/tmp/tb_check.out"
        cmd = [iverilog, "-g2012", "-g2005-sv", "-o", out_bin, rtl_path, tb_path]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except Exception as exc:  # noqa: BLE001
            return f"Syntax check failed to run: {exc}"
        if proc.returncode == 0:
            return None
        return (proc.stderr or proc.stdout or "iverilog reported a compile error").strip()

    def _validate_tb(self, tb_source: str, node_id: str) -> None:
        if not tb_source or not tb_source.strip():
            raise RuntimeError("LLM returned empty testbench.")
        if "module" not in tb_source:
            raise RuntimeError("LLM testbench missing module declaration.")
        if node_id not in tb_source:
            # Not fatal but note it to caller
            raise RuntimeError(f"LLM testbench missing DUT name '{node_id}'.")

    def _hoist_declarations(self, source: str) -> str:
        """Move reg/wire/integer declarations to module scope to appease strict iverilog parsing."""
        lines = source.splitlines()
        timescale_lines = []
        module_header_idx = None
        for idx, line in enumerate(lines):
            if line.strip().startswith("`timescale"):
                timescale_lines.append(line)
            if line.strip().startswith("module "):
                module_header_idx = idx
                break
        if module_header_idx is None:
            return source
        header = lines[: module_header_idx + 1]
        body = lines[module_header_idx + 1 :]
        decls = []
        rest = []
        for line in body:
            stripped = line.strip()
            if stripped.startswith(("reg ", "wire ", "integer ")):
                decls.append(stripped)
            else:
                rest.append(line)
        return "\n".join(header + decls + rest)

    def _balance_blocks(self, source: str) -> str:
        """Balance begin/end tokens to avoid unterminated blocks."""
        import re

        begin_count = len(re.findall(r"\bbegin\b", source))
        end_count = len(re.findall(r"\bend\b", source))
        missing = begin_count - end_count
        if missing > 0:
            source = source.rstrip() + "\n" + "\n".join("end" for _ in range(missing)) + "\n"
        return source
