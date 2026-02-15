"""
Deterministic testbench lint worker. Runs iverilog compile checks plus
lightweight semantic checks on checker/reset/timing patterns.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pika

from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_retry_count, next_retry_headers, MAX_RETRIES

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"

_PROC_START_RE = re.compile(r"(?im)^\s*(always\s*@\s*\(([^)]*)\)|initial)(?:\s|$)")
_RESET_GATING_HINTS = (
    "seen_reset",
    "post_reset",
    "after_reset",
    "reset_done",
    "reset_released",
    "in_reset",
)


class TestbenchLintWorker(threading.Thread):
    __test__ = False

    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self.iverilog = os.getenv("IVERILOG_PATH") or shutil.which("iverilog")

    def run(self) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.basic_qos(prefetch_count=1)
            for method, props, body in ch.consume("process_tasks", inactivity_timeout=0.5):
                if self.stop_event.is_set():
                    break
                if body is None:
                    continue
                try:
                    task = TaskMessage.model_validate_json(body)
                except Exception:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                if task.task_type.value != "TestbenchLinterWorker":
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    continue
                try:
                    result = self.handle_task(task)
                except TaskInputError:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except RetryableError:
                    retry_count = get_retry_count(props)
                    if retry_count < MAX_RETRIES:
                        headers = next_retry_headers(props)
                        ch.basic_publish(
                            exchange=TASK_EXCHANGE,
                            routing_key=task.entity_type.value,
                            body=body,
                            properties=pika.BasicProperties(content_type="application/json", headers=headers),
                        )
                        ch.basic_ack(method.delivery_tag)
                    else:
                        ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except Exception as exc:  # noqa: BLE001
                    result = ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=f"Unhandled testbench lint error: {exc}",
                    )
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        rtl_path = task.context.get("rtl_path")
        tb_path = task.context.get("tb_path")
        if not rtl_path:
            raise TaskInputError("Missing rtl_path in task context.")
        if not tb_path:
            raise TaskInputError("Missing tb_path in task context.")
        rtl_paths = task.context.get("rtl_paths") or [rtl_path]
        if not isinstance(rtl_paths, list):
            rtl_paths = [rtl_path]
        rtl_paths = [str(path) for path in rtl_paths if path]
        if not rtl_paths:
            raise TaskInputError("Missing rtl_paths in task context.")
        missing_rtl = [path for path in rtl_paths if not Path(path).exists()]
        if missing_rtl:
            raise TaskInputError(f"RTL missing: {missing_rtl}")
        rtl_file = Path(rtl_path)
        tb_file = Path(tb_path)
        if not tb_file.exists():
            raise TaskInputError(f"Testbench missing: {tb_file}")
        if not self.iverilog:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="Icarus not found; set IVERILOG_PATH or install iverilog.",
            )
        try:
            rtl_args = list(dict.fromkeys(rtl_paths))
            cmd = [self.iverilog, "-g2012", "-g2005-sv", "-tnull", *rtl_args, str(tb_file)]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if completed.returncode != 0:
                output = completed.stderr or completed.stdout or "Testbench lint failed."
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=None,
                    log_output=output,
                )
            semantic_enabled = os.getenv("TB_LINT_SEMANTIC", "1") != "0"
            semantic_strict = os.getenv("TB_LINT_SEMANTIC_STRICT", "1") != "0"
            semantic_issues: list[str] = []
            if semantic_enabled:
                clocking_raw = task.context.get("clocking")
                clocking = clocking_raw if isinstance(clocking_raw, dict) else {}
                clock_name = str(clocking.get("clock_name", "clk") or "clk")
                reset_name_raw = clocking.get("reset_name")
                reset_name = str(reset_name_raw).strip() if reset_name_raw else None
                reset_polarity = str(clocking.get("reset_polarity", "ACTIVE_LOW")).upper()
                reset_active_low = reset_polarity in {"ACTIVE_LOW", "LOW", "0"}
                semantic_issues = _run_tb_semantic_lint(
                    tb_text=tb_file.read_text(),
                    clock_name=clock_name,
                    reset_name=reset_name,
                    reset_active_low=reset_active_low,
                )
                if semantic_issues and semantic_strict:
                    compile_log = (completed.stdout or completed.stderr or "").strip()
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=_format_semantic_failure_log(semantic_issues, compile_log),
                    )
            log = completed.stdout or "Testbench lint passed."
            if semantic_enabled:
                if semantic_issues:
                    log = (
                        f"{log.rstrip()}\n"
                        "[tb_semantic] WARN\n"
                        f"{_format_semantic_issues(semantic_issues)}"
                    ).strip()
                else:
                    log = f"{log.rstrip()}\n[tb_semantic] PASS".strip()
        except subprocess.TimeoutExpired as exc:
            raise RetryableError(f"Testbench lint timeout: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Testbench lint failed: {exc}",
            )
        emit_runtime_event(
            runtime="worker_tb_lint",
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "artifacts_path": str(tb_file)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(tb_file),
            log_output=log,
        )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


def _run_tb_semantic_lint(
    *,
    tb_text: str,
    clock_name: str,
    reset_name: str | None,
    reset_active_low: bool,
) -> list[str]:
    issues: list[str] = []
    regions = list(_iter_procedural_regions(tb_text))
    has_checker = _looks_self_checking_testbench(tb_text)
    issues.extend(_check_clock_has_single_driver(regions, clock_name))
    if has_checker:
        issues.extend(_check_checker_reset_gating(regions, tb_text, reset_name, reset_active_low))
        issues.extend(_check_stale_reference_compare(regions))
        issues.extend(_check_reset_assertion(tb_text, reset_name, reset_active_low))
    # Keep deterministic ordering for stable logs/narrative.
    return sorted(set(issues))


def _iter_procedural_regions(tb_text: str) -> list[dict]:
    matches = list(_PROC_START_RE.finditer(tb_text))
    regions: list[dict] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(tb_text)
        region_text = tb_text[start:end]
        sensitivity = (match.group(2) or "").strip().lower()
        line = tb_text.count("\n", 0, start) + 1
        regions.append({"text": region_text, "sensitivity": sensitivity, "line": line})
    return regions


def _looks_self_checking_testbench(tb_text: str) -> bool:
    lowered = tb_text.lower()
    if "$finish(1" in lowered or "fail cycle=" in lowered:
        return True
    if "!== ref_" in lowered or "!= ref_" in lowered:
        return True
    return False


def _check_clock_has_single_driver(regions: list[dict], clock_name: str) -> list[str]:
    if not clock_name:
        return []
    assignment_re = re.compile(rf"\b{re.escape(clock_name)}\b\s*(?:<=|=)\s*")
    driver_lines: list[int] = []
    for region in regions:
        if assignment_re.search(region["text"]):
            driver_lines.append(int(region["line"]))
    if len(driver_lines) <= 1:
        return []
    joined = ", ".join(str(v) for v in driver_lines)
    return [
        f"TBSEM001 L{driver_lines[0]}: clock '{clock_name}' is assigned in multiple procedural regions ({joined}). Use one clock driver block."
    ]


def _check_checker_reset_gating(
    regions: list[dict],
    tb_text: str,
    reset_name: str | None,
    reset_active_low: bool,
) -> list[str]:
    if not reset_name:
        return []
    issues: list[str] = []
    first_reset_value = _first_literal_assignment(tb_text, reset_name)
    gate_hints = tuple(token.lower() for token in _RESET_GATING_HINTS)
    raw_gate_re = (
        re.compile(rf"\bif\s*\(\s*{re.escape(reset_name)}\s*\)", flags=re.IGNORECASE)
        if reset_active_low
        else re.compile(rf"\bif\s*\(\s*!\s*{re.escape(reset_name)}\s*\)", flags=re.IGNORECASE)
    )
    reset_mention_re = re.compile(re.escape(reset_name), flags=re.IGNORECASE)
    for region in regions:
        text = region["text"]
        lowered = text.lower()
        if "$finish(1" not in lowered and "fail" not in lowered:
            continue
        if "!=" not in text and "!==" not in text:
            continue
        has_reset_mention = reset_mention_re.search(text) is not None
        has_gate_hint = any(token in lowered for token in gate_hints)
        if not has_reset_mention and not has_gate_hint:
            issues.append(
                f"TBSEM002 L{region['line']}: checker appears ungated by reset/post-reset state."
            )
            continue
        # If reset starts deasserted and checker only gates on raw reset, cycle-0 X comparisons are likely.
        if first_reset_value is not None:
            expected_start = 0 if reset_active_low else 1
            starts_deasserted = first_reset_value != expected_start
            if starts_deasserted and raw_gate_re.search(text) and not has_gate_hint:
                issues.append(
                    f"TBSEM003 L{region['line']}: checker gates only on raw reset while reset starts deasserted. Add post-reset stabilization gating."
                )
    return issues


def _check_stale_reference_compare(regions: list[dict]) -> list[str]:
    issues: list[str] = []
    compare_re = re.compile(r"(?:!==|!=)\s*(ref_[A-Za-z_]\w*)")
    for region in regions:
        text = region["text"]
        lowered = text.lower()
        if "$finish(1" not in lowered and "fail" not in lowered:
            continue
        for match in compare_re.finditer(text):
            ref_var = match.group(1)
            assign_re = re.compile(rf"\b{re.escape(ref_var)}\b\s*(?:<=|=)\s*")
            assign_positions = [assign_match.start() for assign_match in assign_re.finditer(text)]
            if any(pos > match.start() for pos in assign_positions):
                line_offset = text.count("\n", 0, match.start())
                line = int(region["line"]) + line_offset
                issues.append(
                    f"TBSEM004 L{line}: checker compares against '{ref_var}' before updating it in the same procedural region."
                )
    return issues


def _check_reset_assertion(tb_text: str, reset_name: str | None, reset_active_low: bool) -> list[str]:
    if not reset_name:
        return []
    required_value = 0 if reset_active_low else 1
    if _has_literal_assignment(tb_text, reset_name, required_value):
        return []
    level = "low" if reset_active_low else "high"
    return [f"TBSEM005 L1: reset '{reset_name}' is never explicitly driven {level} in the testbench."]


def _first_literal_assignment(tb_text: str, signal_name: str) -> int | None:
    assign_re = re.compile(rf"\b{re.escape(signal_name)}\b\s*(?:<=|=)\s*([^;]+);")
    for match in assign_re.finditer(tb_text):
        value = _parse_logic_literal(match.group(1))
        if value is not None:
            return value
    return None


def _has_literal_assignment(tb_text: str, signal_name: str, value: int) -> bool:
    assign_re = re.compile(rf"\b{re.escape(signal_name)}\b\s*(?:<=|=)\s*([^;]+);")
    for match in assign_re.finditer(tb_text):
        parsed = _parse_logic_literal(match.group(1))
        if parsed == value:
            return True
    return False


def _parse_logic_literal(expr: str) -> int | None:
    text = expr.strip().lower()
    if text in {"1", "1'b1", "'1"}:
        return 1
    if text in {"0", "1'b0", "'0"}:
        return 0
    return None


def _format_semantic_issues(issues: list[str]) -> str:
    return "\n".join(f"- {issue}" for issue in issues)


def _format_semantic_failure_log(issues: list[str], compile_log: str) -> str:
    parts = ["Testbench semantic lint failed.", _format_semantic_issues(issues)]
    if compile_log:
        parts.append("[compile]")
        parts.append(compile_log)
    return "\n".join(parts).strip()
