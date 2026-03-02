"""
Deterministic testbench lint worker. Runs iverilog compile checks plus
lightweight semantic checks on checker/reset/timing patterns.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pika

from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_max_retries, get_retry_count, next_retry_headers
from core.runtime.broker import DEFAULT_RESULTS_ROUTING_KEY, TASK_EXCHANGE, resolve_task_queue
from core.runtime.config import get_runtime_config

_PROC_START_RE = re.compile(r"(?im)^\s*(always\s*@\s*\(([^)]*)\)|initial)(?:\s|$)")
_COMPARE_IF_RE = re.compile(r"if\s*\(([^)]*(?:!==|!=)[^)]*)\)", flags=re.IGNORECASE | re.DOTALL)
_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
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
    queue_name = resolve_task_queue("TestbenchLinterWorker") or "process_tasks"

    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self.iverilog = get_runtime_config().tools.iverilog_path or shutil.which("iverilog")
        self.worker_instance_id = f"worker_tb_lint:{id(self):x}"

    def run(self) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.basic_qos(prefetch_count=1)
            for method, props, body in ch.consume(self.queue_name, inactivity_timeout=0.5):
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
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                received_at = datetime.now(timezone.utc)
                emit_runtime_event(
                    runtime="worker_tb_lint",
                    event_type="task_received",
                    payload={
                        "task_id": str(task.task_id),
                        "node_id": task.context.get("node_id"),
                        "task_type": task.task_type.value,
                        "run_id": task.run_id,
                        "received_ts": received_at.isoformat(),
                        "worker_instance_id": self.worker_instance_id,
                        "worker_thread_name": self.name,
                        "queue_name": self.queue_name,
                    },
                )
                try:
                    result = self.handle_task(task)
                except TaskInputError:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except RetryableError:
                    retry_count = get_retry_count(props)
                    if retry_count < get_max_retries():
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
                result = result.model_copy(
                    update={
                        "received_at": result.received_at or received_at,
                        "started_at": result.started_at or received_at,
                    }
                )
                self._publish_result(ch, task, result)
                emit_runtime_event(
                    runtime="worker_tb_lint",
                    event_type="task_result_published",
                    payload={
                        "task_id": str(task.task_id),
                        "node_id": task.context.get("node_id"),
                        "task_type": task.task_type.value,
                        "status": result.status.value,
                        "run_id": task.run_id,
                        "worker_instance_id": self.worker_instance_id,
                        "worker_thread_name": self.name,
                        "queue_name": self.queue_name,
                    },
                )
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
            lint_cfg = get_runtime_config().lint
            semantic_enabled = lint_cfg.tb_semantic_enabled
            semantic_strict = lint_cfg.tb_semantic_strict
            semantic_issues: list[str] = []
            if semantic_enabled:
                iface = task.context.get("interface") if isinstance(task.context.get("interface"), dict) else {}
                iface_signals = iface.get("signals") if isinstance(iface, dict) else []
                signal_names: list[str] = []
                if isinstance(iface_signals, list):
                    for item in iface_signals:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("name")
                        if name:
                            signal_names.append(str(name))
                clocking_raw = task.context.get("clocking")
                clocking = _normalize_clocking_context(clocking_raw, signal_names)
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
                    signal_names=signal_names,
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

    def _publish_result(
        self,
        ch: pika.adapters.blocking_connection.BlockingChannel,
        task: TaskMessage,
        result: ResultMessage,
    ) -> None:
        routed = result.model_copy(update={"run_id": result.run_id or task.run_id})
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=task.results_routing_key or DEFAULT_RESULTS_ROUTING_KEY,
            body=routed.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


def _run_tb_semantic_lint(
    *,
    tb_text: str,
    clock_name: str,
    reset_name: str | None,
    reset_active_low: bool,
    signal_names: list[str],
) -> list[str]:
    issues: list[str] = []
    regions = list(_iter_procedural_regions(tb_text))
    has_checker = _looks_self_checking_testbench(tb_text)
    issues.extend(_check_clock_has_single_driver(regions, clock_name))
    if has_checker:
        issues.extend(_check_checker_reset_gating(regions, tb_text, reset_name, reset_active_low))
        issues.extend(_check_stale_reference_compare(regions))
        issues.extend(_check_reset_assertion(tb_text, reset_name, reset_active_low))
        issues.extend(_check_checker_delay_dependency(regions))
        issues.extend(_check_mixed_time_and_edge_stimulus(regions, clock_name))
        issues.extend(_check_prev_sampled_control_usage(regions))
        issues.extend(_check_fail_print_consistency(regions, signal_names))
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


def _check_checker_delay_dependency(regions: list[dict]) -> list[str]:
    issues: list[str] = []
    delay_re = re.compile(r"#\s*\d+")
    for region in regions:
        text = _strip_verilog_comments(region["text"])
        lowered = text.lower()
        if "$finish(1" not in lowered and "fail" not in lowered:
            continue
        if "!=" not in text and "!==" not in text:
            continue
        delays = delay_re.findall(text)
        if len(delays) > 2:
            issues.append(
                f"TBSEM006 L{region['line']}: checker compare path depends on excessive delay controls ({', '.join(delays[:4])}). Prefer edge-aligned ordering over chained # delays."
            )
    return issues


def _check_mixed_time_and_edge_stimulus(regions: list[dict], clock_name: str) -> list[str]:
    checker_regions = [r for r in regions if ("$finish(1" in r["text"].lower() or "fail" in r["text"].lower()) and "!=" in r["text"]]
    if not checker_regions:
        return []
    has_edge_checker = any(
        "posedge" in (r["sensitivity"] or "") or "negedge" in (r["sensitivity"] or "")
        for r in checker_regions
    )
    if not has_edge_checker:
        return []
    time_stim_regions = []
    for region in regions:
        text = region["text"]
        lowered = text.lower()
        if "initial" not in lowered:
            continue
        if "@(" in text:
            continue
        if len(re.findall(r"#\s*\d+", text)) < 3:
            continue
        if not re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\b\s*(?:<=|=)\s*", text):
            continue
        if clock_name and re.search(rf"\b{re.escape(clock_name)}\b\s*(?:<=|=)\s*", text):
            # Ignore pure clock generation blocks.
            assign_count = len(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b\s*(?:<=|=)\s*", text))
            if assign_count <= 1:
                continue
        time_stim_regions.append(region["line"])
    if not time_stim_regions:
        return []
    return [
        f"TBSEM007 L{time_stim_regions[0]}: testbench mixes delay-based stimulus in initial blocks with edge-based checker logic. Drive stimulus on explicit clock edges for deterministic sampling."
    ]


def _check_prev_sampled_control_usage(regions: list[dict]) -> list[str]:
    issues: list[str] = []
    for region in regions:
        text = region["text"]
        lowered = text.lower()
        if "$finish(1" not in lowered and "fail" not in lowered:
            continue
        if "prev_" not in text:
            continue
        if "!=" not in text and "!==" not in text:
            continue
        if re.search(r"#\s*\d+", text):
            issues.append(
                f"TBSEM008 L{region['line']}: checker uses sampled prev_* controls with delay controls. This often indicates stale-control comparisons across cycles."
            )
    return issues


def _check_fail_print_consistency(regions: list[dict], signal_names: list[str]) -> list[str]:
    issues: list[str] = []
    signal_set = {name for name in signal_names if isinstance(name, str)}
    for region in regions:
        text = region["text"]
        lowered = text.lower()
        if "$display" not in lowered:
            continue
        if "$finish(1" not in lowered and "fail" not in lowered:
            continue
        cmp_match = _COMPARE_IF_RE.search(text)
        if not cmp_match:
            continue
        cmp_expr = cmp_match.group(1)
        cmp_ids = {name for name in _IDENT_RE.findall(cmp_expr) if name in signal_set}
        display_ids = _extract_display_identifiers(text)
        if not display_ids:
            continue
        missing = sorted(name for name in cmp_ids if name not in display_ids)
        prev_only_print = any(name.startswith("prev_") for name in display_ids) and not any(name.startswith("prev_") for name in cmp_ids)
        if missing:
            issues.append(
                f"TBSEM009 L{region['line']}: FAIL print omits compared DUT/expected signal(s): {', '.join(missing)}."
            )
        if prev_only_print:
            issues.append(
                f"TBSEM010 L{region['line']}: FAIL print relies on prev_* sampled controls while compare expression is current-cycle. Include compare-context controls/signals explicitly."
            )
    return issues


def _extract_display_identifiers(text: str) -> set[str]:
    ids: set[str] = set()
    display_re = re.compile(r"\$display\s*\((.*?)\);", flags=re.DOTALL)
    for match in display_re.finditer(text):
        body = match.group(1)
        if not body:
            continue
        # Drop format string prefix if present.
        body = re.sub(r'^\s*"[^"]*"\s*,?', "", body, count=1, flags=re.DOTALL)
        for ident in _IDENT_RE.findall(body):
            if ident in {"display", "time", "finish"}:
                continue
            ids.add(ident)
    return ids


def _normalize_clocking_context(raw_clocking, signal_names: list[str]) -> dict:
    item = {}
    if isinstance(raw_clocking, dict):
        item = raw_clocking
    elif isinstance(raw_clocking, list):
        for entry in raw_clocking:
            if isinstance(entry, dict):
                item = entry
                break
    reset_name = item.get("reset_name")
    if not reset_name:
        lowered = {str(name).lower(): str(name) for name in signal_names if isinstance(name, str)}
        for candidate in ("rst_n", "reset_n", "rst", "reset"):
            if candidate in lowered:
                reset_name = lowered[candidate]
                break
    reset_polarity = item.get("reset_polarity")
    if not reset_polarity:
        reset_polarity = "ACTIVE_LOW" if str(reset_name or "").lower().endswith("_n") else "ACTIVE_HIGH"
    return {
        "clock_name": item.get("clock_name") or "clk",
        "clock_polarity": item.get("clock_polarity") or "POSEDGE",
        "reset_name": reset_name,
        "reset_polarity": reset_polarity,
        "reset_is_async": item.get("reset_is_async"),
    }


def _strip_verilog_comments(text: str) -> str:
    # Remove // line comments and /* ... */ blocks before pattern scans.
    no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    no_line = re.sub(r"//.*", "", no_block)
    return no_line


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
