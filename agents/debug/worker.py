"""
Debug agent runtime. Uses LLM to propose fixes based on task memory logs.
Fails hard if the LLM or inputs are unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from hashlib import sha256
from pathlib import Path

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, init_llm_gateway
from agents.common.tb_sanitizer import sanitize_testbench
from core.observability.agentops_tracker import get_tracker
from core.runtime.retry import TaskInputError


class DebugWorker(AgentWorkerBase):
    handled_types = {AgentType.DEBUG}
    runtime_name = "agent_debug"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        if not self.gateway or not Message or not GenerationConfig:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output="LLM gateway unavailable; set USE_LLM=1 and configure provider credentials.",
            )

        ctx = task.context
        if "node_id" not in ctx:
            raise TaskInputError("Missing node_id in task context.")
        node_id = ctx["node_id"]
        rtl_path = Path(ctx.get("rtl_path", "")) if ctx.get("rtl_path") else None
        tb_path = Path(ctx.get("tb_path", "")) if ctx.get("tb_path") else None
        if rtl_path is None:
            raise TaskInputError("Missing rtl_path in task context.")
        if tb_path is None:
            tb_path = rtl_path.with_name(f"{node_id}_tb.sv")

        sim_attempt = _parse_attempt(ctx.get("attempt"))
        debug_reason = str(ctx.get("debug_reason", "")).strip().lower() or "sim"
        task_memory_root = Path("artifacts/task_memory") / node_id

        rtl_text = rtl_path.read_text() if rtl_path.exists() else ""
        tb_text = tb_path.read_text() if tb_path.exists() else ""

        # Attempt-aware logs/insights. Fall back to legacy stage names when attempt is missing.
        lint_log = _read_optional_text(task_memory_root / _stage_dir("lint", sim_attempt) / "log.txt")
        sim_log = _read_optional_text(task_memory_root / _stage_dir("sim", sim_attempt) / "log.txt")
        tb_lint_log = _read_optional_text(task_memory_root / _stage_dir("tb_lint", sim_attempt) / "log.txt")
        distilled = _read_optional_text(task_memory_root / _stage_dir("distill", sim_attempt) / "distilled_dataset.json")
        reflection = _read_optional_text(task_memory_root / _stage_dir("reflect", sim_attempt) / "reflection_insights.json")

        system = (
            "You are a Debug Agent for an RTL design pipeline. Your job is to PATCH CODE.\n"
            "You will be given the current RTL, the current testbench, and failure evidence (sim/tb_lint logs and reflection insights).\n"
            "Return ONLY valid JSON (no extra text, no code fences). Format:\n"
            "{\n"
            '  \"summary\": string,\n'
            '  \"touched_files\": [\"rtl\"|\"tb\", ...],\n'
            '  \"rtl_lines\": [string, ...] | null,\n'
            '  \"tb_lines\": [string, ...] | null,\n'
            '  \"risks\": [string, ...],\n'
            '  \"next_steps\": [string, ...]\n'
            "}\n"
            "Rules:\n"
            "- If you touch RTL, rtl_lines MUST be a complete synthesizable Verilog-2001 module named exactly as the DUT.\n"
            "- If you touch the testbench, tb_lines MUST be a complete Verilog-2001 testbench module named tb_<DUT>.\n"
            "- Preserve the DUT port interface exactly (no new ports, no renames).\n"
            "- Avoid SystemVerilog-only keywords (no always_ff/always_comb/logic/interfaces).\n"
            "- For testbenches: strict Verilog-2001 compatibility (no declarations inside procedural blocks; no reg/integer declaration-time init with function calls).\n"
            "- Do NOT include newline characters inside JSON strings; each entry in *_lines is a single line.\n"
            "- If debug_reason indicates a lint failure, prioritize making the relevant artifact lint-clean (Verilator/Icarus).\n"
            "- For sim failures, do not assume the RTL is wrong: check for common testbench issues like stimulus timing races.\n"
            "  If the testbench drives inputs immediately after an @(posedge clk) (same timestep as the sampling edge),\n"
            "  it can race the DUT/reference model and cause deterministic mismatches. Prefer driving on negedge (or add a small #1 delay).\n"
            "- If waveform dumping uses a cycle window, do NOT treat DUMP_START=0 as \"disabled\"; some benches accidentally $dumpoff forever.\n"
            "- If the context includes child modules and connection wiring, preserve the integration structure; only fix wiring or glue logic as needed.\n"
        )
        user = (
            f"Node: {node_id}\n"
            f"Attempt: {sim_attempt if sim_attempt is not None else 'unknown'}\n"
            f"Debug reason: {debug_reason}\n"
            f"Context:\n{json.dumps(ctx, indent=2)}\n\n"
            "Current RTL (verbatim):\n"
            f"{rtl_text}\n\n"
            "Current testbench (verbatim):\n"
            f"{tb_text}\n\n"
            "RTL lint log (if any):\n"
            f"{lint_log}\n\n"
            "Simulation log (if any):\n"
            f"{sim_log}\n\n"
            "Testbench lint log (if any):\n"
            f"{tb_lint_log}\n\n"
            "Distilled dataset (if any):\n"
            f"{distilled}\n\n"
            "Reflection insights (if any):\n"
            f"{reflection}\n"
        )
        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_DEBUG", "10000"))
        temperature = float(os.getenv("LLM_TEMPERATURE_DEBUG", "0.2"))
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens)

        stage_dir = Path("artifacts/task_memory") / node_id / _stage_dir("debug", sim_attempt)
        try:
            stage_dir.mkdir(parents=True, exist_ok=True)
            prompt_payload = [
                {"role": getattr(m.role, "value", str(m.role)), "content": m.content} for m in msgs  # type: ignore[attr-defined]
            ]
            (stage_dir / "prompt_messages.json").write_text(json.dumps(prompt_payload, indent=2), encoding="utf-8")
        except Exception:
            pass

        max_attempts = int(os.getenv("DEBUG_MAX_ATTEMPTS", "3"))
        last_error: str | None = None
        for llm_attempt in range(1, max_attempts + 1):
            try:
                resp = asyncio.run(self.gateway.generate(messages=msgs, config=cfg))  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                last_error = f"Debug LLM call failed: {exc}"
                if llm_attempt < max_attempts:
                    continue
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    log_output=last_error,
                )

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
                    metadata={"stage": "debug", "attempt": llm_attempt},
                )
            except Exception:
                pass

            try:
                (stage_dir / f"llm_raw_attempt{llm_attempt}.txt").write_text(resp.content, encoding="utf-8")
            except Exception:
                pass

            parsed = _safe_json(resp.content)
            if parsed:
                try:
                    (stage_dir / f"llm_parsed_attempt{llm_attempt}.json").write_text(
                        json.dumps(parsed, indent=2),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                try:
                    write_result = _apply_debug_patch(
                        node_id=node_id,
                        attempt=sim_attempt,
                        rtl_path=rtl_path,
                        tb_path=tb_path,
                        payload=parsed,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = f"Debug patch application failed: {exc}"
                    if llm_attempt < max_attempts:
                        continue
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        log_output=last_error,
                    )
                if not write_result["touched_files"]:
                    last_error = "Debug agent returned no patch (touched_files empty)."
                    if llm_attempt < max_attempts:
                        continue
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        log_output=last_error,
                    )
                emit_runtime_event(
                    runtime=self.runtime_name,
                    event_type="task_completed",
                    payload={"task_id": str(task.task_id)},
                )
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.SUCCESS,
                    artifacts_path=str(rtl_path),
                    log_output=write_result["log_output"],
                    reflections=json.dumps(
                        {
                            "summary": parsed.get("summary", ""),
                            "touched_files": write_result["touched_files"],
                            "attempt": sim_attempt,
                            "debug_reason": debug_reason,
                            "rtl_sha256": write_result.get("rtl_sha256"),
                            "tb_sha256": write_result.get("tb_sha256"),
                            "risks": parsed.get("risks", []),
                            "next_steps": parsed.get("next_steps", []),
                        },
                        indent=2,
                    ),
                )
            last_error = "Debug LLM response was not valid JSON."
            if llm_attempt < max_attempts:
                continue
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=last_error,
            )

        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.FAILURE,
            log_output=last_error or "Debug LLM response was not valid JSON.",
        )


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


_NO_FENCE_PREFIXES = ("```", "`systemverilog")


def _parse_attempt(value) -> int | None:
    if value is None:
        return None
    try:
        attempt = int(value)
    except Exception:
        return None
    return attempt if attempt > 0 else None


def _stage_dir(kind: str, attempt: int | None) -> str:
    if attempt is None:
        return kind
    return f"{kind}_attempt{attempt}"


def _read_optional_text(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text()
    except Exception:
        return ""
    return ""


def _sanitize_verilog(source: str, *, kind: str) -> str:
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(_NO_FENCE_PREFIXES):
            continue
        lines.append(line)
    text = "\n".join(lines)
    if kind == "rtl":
        text = text.replace("always_ff", "always")
        text = text.replace("always_comb", "always @*")
        if "always" in text:
            text = text.replace("output logic", "output reg")
            text = text.replace("output wire", "output reg")
        text = text.replace("logic", "wire")
        return text
    if kind == "tb":
        text = text.replace("logic", "reg")
        text = re.sub(r"\$stop\s*(\([^;]*\))?\s*;", "$finish;", text)
        # Fix common LLM mistake: $value$plusargs("DUMP") is invalid for Icarus.
        text = re.sub(r"\$value\$plusargs\s*\(\s*(['\"])DUMP\1\s*\)", r"$test$plusargs(\1DUMP\1)", text)
        if not text.strip().startswith("`timescale"):
            text = "`timescale 1ns/1ps\n\n" + text
        if "endmodule" not in text:
            text = text.rstrip() + "\nendmodule\n"
        return sanitize_testbench(text)
    return source


def _apply_debug_patch(
    *,
    node_id: str,
    attempt: int | None,
    rtl_path: Path,
    tb_path: Path,
    payload: dict,
) -> dict:
    touched = payload.get("touched_files") or []
    if not isinstance(touched, list):
        touched = []
    touched_norm = []
    for entry in touched:
        if not isinstance(entry, str):
            continue
        val = entry.strip().lower()
        if val in ("rtl", "tb"):
            touched_norm.append(val)
    touched_norm = sorted(set(touched_norm))

    wrote_rtl = False
    wrote_tb = False
    rtl_sha = None
    tb_sha = None

    if "rtl" in touched_norm:
        rtl_lines = payload.get("rtl_lines")
        if not isinstance(rtl_lines, list) or not rtl_lines:
            raise ValueError("touched_files includes 'rtl' but rtl_lines is missing/empty")
        rtl_source = "\n".join(str(line) for line in rtl_lines)
        rtl_source = _sanitize_verilog(rtl_source, kind="rtl")
        rtl_path.parent.mkdir(parents=True, exist_ok=True)
        rtl_path.write_text(rtl_source)
        rtl_sha = sha256(rtl_source.encode()).hexdigest()
        wrote_rtl = True

    if "tb" in touched_norm:
        tb_lines = payload.get("tb_lines")
        if not isinstance(tb_lines, list) or not tb_lines:
            raise ValueError("touched_files includes 'tb' but tb_lines is missing/empty")
        tb_source = "\n".join(str(line) for line in tb_lines)
        tb_source = _sanitize_verilog(tb_source, kind="tb")
        tb_path.parent.mkdir(parents=True, exist_ok=True)
        tb_path.write_text(tb_source)
        tb_sha = sha256(tb_source.encode()).hexdigest()
        wrote_tb = True

    # Snapshot patched artifacts under task_memory for traceability across attempts.
    if attempt is not None:
        stage_dir = Path("artifacts/task_memory") / node_id / _stage_dir("debug", attempt)
        stage_dir.mkdir(parents=True, exist_ok=True)
        if wrote_rtl:
            (stage_dir / f"patched_{node_id}.sv").write_text(rtl_path.read_text())
        if wrote_tb:
            (stage_dir / f"patched_{node_id}_tb.sv").write_text(tb_path.read_text())

    touched_out = []
    if wrote_rtl:
        touched_out.append("rtl")
    if wrote_tb:
        touched_out.append("tb")

    return {
        "touched_files": touched_out,
        "rtl_sha256": rtl_sha,
        "tb_sha256": tb_sha,
        "log_output": (
            f"Debug patched {node_id}: touched={touched_out} "
            f"(attempt={attempt if attempt is not None else 'unknown'})."
        ),
    }
