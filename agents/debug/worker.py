"""
Debug agent runtime. Uses LLM to propose fixes based on task memory logs.
Fails hard if the LLM or inputs are unavailable.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, init_llm_gateway
from agents.common.tb_sanitizer import sanitize_testbench
from workers.lint.worker import _format_semantic_issues, _run_rtl_semantic_lint
from workers.tb_lint.worker import (
    _format_semantic_failure_log as _format_tb_semantic_failure_log,
    _format_semantic_issues as _format_tb_semantic_issues,
    _normalize_clocking_context as _normalize_tb_clocking_context,
    _run_tb_semantic_lint,
)
from core.observability.agentops_tracker import get_tracker
from core.runtime.retry import TaskInputError
from core.runtime.config import get_runtime_config

_VERILATOR_QUIET_UNSUPPORTED_RE = re.compile(r"invalid option:\s*--quiet", re.IGNORECASE)
_SIM_FAIL_MARKER_RE = re.compile(r"\b(FAIL|FAILURE|ERROR|FATAL|ASSERT|ASSERTION)\b", re.IGNORECASE)


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
        rtl_prompt = _truncate_prompt_text(rtl_text, max_chars=18000)
        tb_prompt = _truncate_prompt_text(tb_text, max_chars=18000)
        lint_log_prompt = _truncate_prompt_text(lint_log, max_chars=8000)
        sim_log_prompt = _truncate_prompt_text(sim_log, max_chars=8000)
        tb_lint_log_prompt = _truncate_prompt_text(tb_lint_log, max_chars=8000)
        distilled_prompt = _truncate_prompt_text(distilled, max_chars=10000)
        reflection_prompt = _truncate_prompt_text(reflection, max_chars=10000)

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
            "- If attempt_history is provided, avoid repeating a previously attempted patch strategy for the same failure_signature.\n"
            "- If stuck=true or a failure signature repeats, your patch MUST change strategy materially and explain the delta in summary.\n"
            "- If waveform dumping uses a cycle window, do NOT treat DUMP_START=0 as \"disabled\"; some benches accidentally $dumpoff forever.\n"
            "- If the context includes child modules and connection wiring, preserve the integration structure; only fix wiring or glue logic as needed.\n"
            "- Your patch is accepted only if local deterministic validation passes (tb_lint for TB changes; lint for RTL changes; sim check for smoke-child sim failures).\n"
        )
        user = (
            f"Node: {node_id}\n"
            f"Attempt: {sim_attempt if sim_attempt is not None else 'unknown'}\n"
            f"Debug reason: {debug_reason}\n"
            f"Context:\n{json.dumps(ctx, indent=2)}\n\n"
            "Current RTL (verbatim):\n"
            f"{rtl_prompt}\n\n"
            "Current testbench (verbatim):\n"
            f"{tb_prompt}\n\n"
            "RTL lint log (if any):\n"
            f"{lint_log_prompt}\n\n"
            "Simulation log (if any):\n"
            f"{sim_log_prompt}\n\n"
            "Testbench lint log (if any):\n"
            f"{tb_lint_log_prompt}\n\n"
            "Distilled dataset (if any):\n"
            f"{distilled_prompt}\n\n"
            "Reflection insights (if any):\n"
            f"{reflection_prompt}\n"
        )
        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        llm_cfg = get_runtime_config().llm
        max_tokens = int(llm_cfg.max_tokens_debug)
        temperature = float(llm_cfg.temperature_debug)
        top_p = llm_cfg.top_p
        cfg = GenerationConfig(temperature=temperature, top_p=top_p, max_tokens=max_tokens)

        stage_dir = Path("artifacts/task_memory") / node_id / _stage_dir("debug", sim_attempt)
        try:
            stage_dir.mkdir(parents=True, exist_ok=True)
            prompt_payload = [
                {"role": getattr(m.role, "value", str(m.role)), "content": m.content} for m in msgs  # type: ignore[attr-defined]
            ]
            (stage_dir / "prompt_messages.json").write_text(json.dumps(prompt_payload, indent=2), encoding="utf-8")
        except Exception:
            pass

        max_attempts = int(get_runtime_config().debug.max_attempts)
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
                local_validation = _run_local_validation(
                    ctx=ctx,
                    rtl_path=rtl_path,
                    tb_path=tb_path,
                    touched_files=write_result["touched_files"],
                    debug_reason=debug_reason,
                )
                try:
                    (stage_dir / f"local_validation_attempt{llm_attempt}.txt").write_text(
                        local_validation["details"],
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                if not local_validation["ok"]:
                    last_error = (
                        "Debug local validation failed "
                        f"(llm_attempt={llm_attempt}/{max_attempts}): {local_validation['summary']}\n"
                        f"{local_validation['details']}"
                    )
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
                final_log = (
                    f"{write_result['log_output']} "
                    f"Local validation passed: {local_validation['summary']} "
                    f"(llm_attempt={llm_attempt}/{max_attempts})."
                )
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.SUCCESS,
                    artifacts_path=str(rtl_path),
                    log_output=final_log,
                    reflections=json.dumps(
                        {
                            "summary": parsed.get("summary", ""),
                            "touched_files": write_result["touched_files"],
                            "attempt": sim_attempt,
                            "debug_reason": debug_reason,
                            "rtl_sha256": write_result.get("rtl_sha256"),
                            "tb_sha256": write_result.get("tb_sha256"),
                            "local_validation": local_validation.get("checks", []),
                            "llm_attempts_used": llm_attempt,
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


def _truncate_prompt_text(text: str, *, max_chars: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n... [truncated {omitted} char(s) for prompt efficiency]"


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
        existing_rtl = rtl_path.read_text() if rtl_path.exists() else ""
        if rtl_source != existing_rtl:
            rtl_path.parent.mkdir(parents=True, exist_ok=True)
            rtl_path.write_text(rtl_source)
            wrote_rtl = True
        rtl_sha = sha256(rtl_source.encode()).hexdigest()

    if "tb" in touched_norm:
        tb_lines = payload.get("tb_lines")
        if not isinstance(tb_lines, list) or not tb_lines:
            raise ValueError("touched_files includes 'tb' but tb_lines is missing/empty")
        tb_source = "\n".join(str(line) for line in tb_lines)
        tb_source = _sanitize_verilog(tb_source, kind="tb")
        existing_tb = tb_path.read_text() if tb_path.exists() else ""
        if tb_source != existing_tb:
            tb_path.parent.mkdir(parents=True, exist_ok=True)
            tb_path.write_text(tb_source)
            wrote_tb = True
        tb_sha = sha256(tb_source.encode()).hexdigest()

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


def _run_local_validation(
    *,
    ctx: dict,
    rtl_path: Path,
    tb_path: Path,
    touched_files: list[str],
    debug_reason: str,
) -> dict:
    checks: list[dict] = []

    need_rtl_lint = ("rtl" in touched_files) or (debug_reason == "rtl_lint")
    need_tb_lint = ("tb" in touched_files) or (debug_reason == "tb_lint")
    need_sim = (
        debug_reason == "sim"
        and _is_smoke_child_context(ctx)
        and (("rtl" in touched_files) or ("tb" in touched_files))
    )
    rtl_paths = _resolve_rtl_paths(ctx, rtl_path)

    if need_rtl_lint:
        checks.append(_run_rtl_lint_check(ctx=ctx, rtl_paths=rtl_paths, rtl_path=rtl_path))
    if need_tb_lint:
        checks.append(_run_tb_lint_check(ctx=ctx, rtl_paths=rtl_paths, tb_path=tb_path))
    if need_sim:
        checks.append(_run_sim_check(rtl_paths, tb_path))

    if not checks:
        return {
            "ok": True,
            "summary": "no local checks required",
            "details": "No local checks were required for this patch.",
            "checks": [],
        }

    ok = all(bool(check.get("ok")) for check in checks)
    summary = ", ".join(f"{check['name']}={'PASS' if check['ok'] else 'FAIL'}" for check in checks)
    details_lines: list[str] = []
    for check in checks:
        details_lines.append(f"[{check['name']}] {'PASS' if check['ok'] else 'FAIL'}")
        output = str(check.get("output", "")).strip()
        if output:
            details_lines.append(output)
    details = "\n".join(details_lines).strip()
    return {"ok": ok, "summary": summary, "details": details, "checks": checks}


def _is_smoke_child_context(ctx: dict) -> bool:
    if not isinstance(ctx, dict):
        return False
    node_id = str(ctx.get("node_id") or "").strip()
    top_module = str(ctx.get("top_module") or "").strip()
    if not node_id or not top_module or node_id == top_module:
        return False
    verification = ctx.get("verification")
    if not isinstance(verification, dict):
        return False
    goals = verification.get("test_goals")
    if not isinstance(goals, list):
        return False
    return any("smoke" in str(goal or "").strip().lower() for goal in goals)


def _resolve_rtl_paths(ctx: dict, rtl_path: Path) -> list[str]:
    candidates = ctx.get("rtl_paths") or [str(rtl_path)]
    if not isinstance(candidates, list):
        candidates = [str(rtl_path)]
    out: list[str] = []
    for item in candidates:
        value = str(item).strip()
        if value and value not in out:
            out.append(value)
    fallback = str(rtl_path)
    if fallback not in out:
        out.append(fallback)
    return out


def _run_rtl_lint_check(*, ctx: dict, rtl_paths: list[str], rtl_path: Path) -> dict:
    name = "rtl_lint"
    missing = [path for path in rtl_paths if not Path(path).exists()]
    if missing:
        return {"name": name, "ok": False, "output": f"RTL missing for local lint: {missing}"}

    runtime_cfg = get_runtime_config()
    lint_cfg = runtime_cfg.lint
    verilator = runtime_cfg.tools.verilator_path or shutil.which("verilator")
    if not verilator:
        return {"name": name, "ok": False, "output": "Verilator not found for local debug validation."}

    cmd = [verilator, "--lint-only", "--quiet", "--sv", *rtl_paths]
    timeout_s = float(runtime_cfg.debug.local_lint_timeout_s)
    try:
        completed = _run_subprocess(cmd, timeout_s)
        output = _format_tool_output(completed.stdout, completed.stderr)
        if completed.returncode != 0 and _VERILATOR_QUIET_UNSUPPORTED_RE.search(output):
            fallback = [verilator, "--lint-only", "--sv", *rtl_paths]
            completed = _run_subprocess(fallback, timeout_s)
            fallback_output = _format_tool_output(completed.stdout, completed.stderr)
            output = f"Verilator '--quiet' unsupported; retried without it.\n{fallback_output}".strip()
    except subprocess.TimeoutExpired as exc:
        return {"name": name, "ok": False, "output": f"Verilator local validation timed out: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "ok": False, "output": f"Verilator local validation failed: {exc}"}
    strict_warnings = lint_cfg.verilator_strict_warnings
    fail_moddup = lint_cfg.rtl_fail_moddup
    has_moddup = "MODDUP" in output.upper()
    has_error = ("%Error" in output) or ("%Fatal" in output)
    failed = (completed.returncode != 0 and (strict_warnings or has_error)) or (has_moddup and fail_moddup)
    if failed:
        return {
            "name": name,
            "ok": False,
            "output": output or "Verilator local validation failed.",
        }

    semantic_enabled = lint_cfg.rtl_semantic_enabled
    semantic_strict = lint_cfg.rtl_semantic_strict
    semantic_issues: list[str] = []
    blocking_issues: list[str] = []
    advisory_issues: list[str] = []
    if semantic_enabled:
        semantic_issues = _run_rtl_semantic_lint(
            rtl_text=rtl_path.read_text(),
            module_contract=ctx.get("module_contract") if isinstance(ctx, dict) else None,
        )
        for issue in semantic_issues:
            code = issue.split(" ", 1)[0]
            if code == "RLSEM010":
                advisory_issues.append(issue)
            else:
                blocking_issues.append(issue)
    if blocking_issues and semantic_strict:
        semantic_log = "[rtl_semantic] FAIL\n" + _format_semantic_issues(blocking_issues + advisory_issues)
        if output:
            semantic_log += f"\n{output}"
        return {"name": name, "ok": False, "output": semantic_log}

    merged_output = output or "Verilator local validation passed."
    warn_issues = blocking_issues + advisory_issues
    if warn_issues:
        merged_output = f"{merged_output}\n[rtl_semantic] WARN\n{_format_semantic_issues(warn_issues)}".strip()
    elif semantic_enabled:
        merged_output = f"{merged_output}\n[rtl_semantic] PASS".strip()

    return {
        "name": name,
        "ok": True,
        "output": merged_output,
    }


def _run_tb_lint_check(*, ctx: dict, rtl_paths: list[str], tb_path: Path) -> dict:
    name = "tb_lint"
    missing = [path for path in rtl_paths if not Path(path).exists()]
    if missing:
        return {"name": name, "ok": False, "output": f"RTL missing for local TB lint: {missing}"}
    if not tb_path.exists():
        return {"name": name, "ok": False, "output": f"Testbench missing for local TB lint: {tb_path}"}

    runtime_cfg = get_runtime_config()
    iverilog = runtime_cfg.tools.iverilog_path or shutil.which("iverilog")
    if not iverilog:
        return {"name": name, "ok": False, "output": "Icarus (iverilog) not found for local debug validation."}

    cmd = [iverilog, "-g2012", "-g2005-sv", "-tnull", *rtl_paths, str(tb_path)]
    timeout_s = float(runtime_cfg.debug.local_lint_timeout_s)
    try:
        completed = _run_subprocess(cmd, timeout_s)
    except subprocess.TimeoutExpired as exc:
        return {"name": name, "ok": False, "output": f"TB local validation timed out: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "ok": False, "output": f"TB local validation failed: {exc}"}

    output = _format_tool_output(completed.stdout, completed.stderr)
    if completed.returncode != 0:
        return {
            "name": name,
            "ok": False,
            "output": output or "TB local validation failed.",
        }

    lint_cfg = get_runtime_config().lint
    semantic_enabled = lint_cfg.tb_semantic_enabled
    semantic_strict = lint_cfg.tb_semantic_strict
    semantic_issues: list[str] = []
    if semantic_enabled:
        iface = ctx.get("interface") if isinstance(ctx.get("interface"), dict) else {}
        iface_signals = iface.get("signals") if isinstance(iface, dict) else []
        signal_names: list[str] = []
        if isinstance(iface_signals, list):
            for item in iface_signals:
                if not isinstance(item, dict):
                    continue
                name_field = item.get("name")
                if name_field:
                    signal_names.append(str(name_field))
        clocking_raw = ctx.get("clocking")
        clocking = _normalize_tb_clocking_context(clocking_raw, signal_names)
        clock_name = str(clocking.get("clock_name", "clk") or "clk")
        reset_name_raw = clocking.get("reset_name")
        reset_name = str(reset_name_raw).strip() if reset_name_raw else None
        reset_polarity = str(clocking.get("reset_polarity", "ACTIVE_LOW")).upper()
        reset_active_low = reset_polarity in {"ACTIVE_LOW", "LOW", "0"}
        semantic_issues = _run_tb_semantic_lint(
            tb_text=tb_path.read_text(),
            clock_name=clock_name,
            reset_name=reset_name,
            reset_active_low=reset_active_low,
            signal_names=signal_names,
        )
        if semantic_issues and semantic_strict:
            compile_log = (completed.stdout or completed.stderr or "").strip()
            return {
                "name": name,
                "ok": False,
                "output": _format_tb_semantic_failure_log(semantic_issues, compile_log),
            }

    merged_output = output or "TB local validation passed."
    if semantic_enabled:
        if semantic_issues:
            merged_output = (
                f"{merged_output.rstrip()}\n"
                "[tb_semantic] WARN\n"
                f"{_format_tb_semantic_issues(semantic_issues)}"
            ).strip()
        else:
            merged_output = f"{merged_output.rstrip()}\n[tb_semantic] PASS".strip()

    return {
        "name": name,
        "ok": True,
        "output": merged_output,
    }


def _run_sim_check(rtl_paths: list[str], tb_path: Path) -> dict:
    name = "sim"
    missing = [path for path in rtl_paths if not Path(path).exists()]
    if missing:
        return {"name": name, "ok": False, "output": f"RTL missing for local sim validation: {missing}"}
    if not tb_path.exists():
        return {"name": name, "ok": False, "output": f"Testbench missing for local sim validation: {tb_path}"}

    runtime_cfg = get_runtime_config()
    iverilog = runtime_cfg.tools.iverilog_path or shutil.which("iverilog")
    vvp = runtime_cfg.tools.vvp_path or shutil.which("vvp")
    if not iverilog or not vvp:
        return {"name": name, "ok": False, "output": "Icarus (iverilog/vvp) not found for local sim validation."}

    timeout_s = float(runtime_cfg.debug.local_lint_timeout_s)
    out_path = "/tmp/debug_local_sim.out"
    build_cmd = [iverilog, "-g2012", "-g2005-sv", "-o", out_path, *rtl_paths, str(tb_path)]
    try:
        build = _run_subprocess(build_cmd, timeout_s)
    except subprocess.TimeoutExpired as exc:
        return {"name": name, "ok": False, "output": f"Local sim build timed out: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "ok": False, "output": f"Local sim build failed: {exc}"}
    build_output = _format_tool_output(build.stdout, build.stderr)
    if build.returncode != 0:
        return {
            "name": name,
            "ok": False,
            "output": (build_output or "Local sim build failed."),
        }

    run_cmd = [vvp, out_path]
    try:
        run = _run_subprocess(run_cmd, timeout_s)
    except subprocess.TimeoutExpired as exc:
        return {"name": name, "ok": False, "output": f"Local sim run timed out: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "ok": False, "output": f"Local sim run failed: {exc}"}
    run_output = _format_tool_output(run.stdout, run.stderr)
    marker_fail = bool(_SIM_FAIL_MARKER_RE.search(run_output or ""))
    ok = run.returncode == 0 and not marker_fail
    if ok:
        merged = run_output or "Local sim validation passed."
        return {"name": name, "ok": True, "output": merged}
    reason = []
    if run.returncode != 0:
        reason.append(f"exit_code={run.returncode}")
    if marker_fail:
        reason.append("failure_marker_detected")
    reason_text = ", ".join(reason) if reason else "unknown_failure"
    output = run_output or "Local sim validation failed."
    return {
        "name": name,
        "ok": False,
        "output": f"{output}\n[sim_analysis] {reason_text}".strip(),
    }


def _format_tool_output(stdout: str | None, stderr: str | None) -> str:
    raw = "\n".join(part for part in [stdout or "", stderr or ""] if part).strip()
    if not raw:
        return ""
    lines = raw.splitlines()
    max_lines = int(get_runtime_config().debug.local_lint_max_lines)
    trimmed = lines[:max_lines]
    suffix = "\n... (truncated)" if len(lines) > max_lines else ""
    return "\n".join(trimmed) + suffix


def _run_subprocess(cmd: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
