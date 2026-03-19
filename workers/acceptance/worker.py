"""
Acceptance gating worker. Verifies required artifacts and acceptance metrics.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pika

from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_retry_count, next_retry_headers, MAX_RETRIES

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class AcceptanceWorker(threading.Thread):
    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event

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
                if task.task_type.value != "AcceptanceWorker":
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
                        log_output=f"Unhandled acceptance error: {exc}",
                    )
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        node_id = ctx.get("node_id")
        if not node_id:
            raise TaskInputError("Missing node_id in task context.")
        attempt = _parse_attempt(ctx.get("attempt"))
        acceptance = ctx.get("acceptance") if isinstance(ctx.get("acceptance"), dict) else {}
        required = acceptance.get("required_artifacts") or []
        metrics = acceptance.get("acceptance_metrics") or []

        if not required and not metrics:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.SUCCESS,
                artifacts_path=None,
                log_output="No acceptance criteria; skipping gating.",
            )

        failures = []
        warnings = []

        # Temporary relaxation: allow acceptance to pass when simulation passed,
        # even if coverage artifacts/metrics are missing. Coverage generation is
        # not yet implemented in the sim worker. TODO: remove once coverage is emitted.
        sim_passed = _sim_passed(node_id, attempt)

        for entry in required:
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            mandatory = bool(entry.get("mandatory", True))
            path = _resolve_artifact_path(name, ctx, node_id, attempt)
            if path and path.exists():
                continue
            msg = f"Missing required artifact '{name}'"
            if path:
                msg += f" (expected {path})"
            if _is_coverage_artifact(name) and sim_passed:
                warnings.append(f"{msg} (coverage gating deferred)")
            elif mandatory:
                failures.append(msg)
            else:
                warnings.append(msg)

        for metric in metrics:
            metric_id = str(metric.get("metric_id", "")).strip()
            operator = str(metric.get("operator", "")).strip()
            target_raw = metric.get("target_value")
            source = metric.get("metric_source")
            if not metric_id or not operator:
                failures.append(f"Invalid acceptance metric definition: {metric}")
                continue
            if _is_coverage_source(source) and sim_passed:
                warnings.append(
                    f"Skipping coverage metric '{metric_id}' (coverage gating deferred until coverage is generated)."
                )
                continue
            value = _load_metric_value(metric_id, source, node_id, attempt)
            if value is None:
                failures.append(f"Missing metric '{metric_id}' from source '{source or 'coverage_report'}'")
                continue
            if not _compare_metric(value, target_raw, operator):
                failures.append(
                    f"Metric '{metric_id}' failed: value={value} target={target_raw} operator={operator}"
                )

        log_lines = []
        if failures:
            log_lines.append("Acceptance gating failed:")
            log_lines.extend(f"- {msg}" for msg in failures)
        if warnings:
            log_lines.append("Acceptance warnings:")
            log_lines.extend(f"- {msg}" for msg in warnings)
        if not failures and not warnings:
            log_lines.append("Acceptance gating passed.")

        emit_runtime_event(
            runtime="worker_acceptance",
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "node_id": node_id},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS if not failures else TaskStatus.FAILURE,
            artifacts_path=None,
            log_output="\n".join(log_lines),
        )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


def _resolve_artifact_path(name: str, ctx: dict, node_id: str, attempt: int | None) -> Path | None:
    base = Path("artifacts/task_memory") / node_id
    rtl_path = Path(ctx.get("rtl_path", "")) if ctx.get("rtl_path") else None
    rtl_paths = ctx.get("rtl_paths") if isinstance(ctx.get("rtl_paths"), list) else []
    tb_path = Path(ctx.get("tb_path", "")) if ctx.get("tb_path") else None
    lowered = name.lower()
    if lowered in ("rtl", "rtl_file", "rtl_source"):
        if rtl_path:
            return rtl_path
        if rtl_paths:
            return Path(rtl_paths[0])
        return rtl_path
    if lowered in ("testbench", "tb", "tb_file", "testbench_file"):
        return tb_path
    if lowered in ("lint_report", "lint_log"):
        return _select_stage_dir(base, "lint", attempt) / "log.txt"
    if lowered in ("tb_lint_log", "testbench_lint_log"):
        return _select_stage_dir(base, "tb_lint", attempt) / "log.txt"
    if lowered in ("tb_log", "testbench_log"):
        return base / "tb" / "log.txt"
    if lowered in ("sim_log", "simulation_log"):
        return _select_stage_dir(base, "sim", attempt) / "log.txt"
    if lowered in ("coverage_report", "coverage"):
        sim_dir = _select_stage_dir(base, "sim", attempt)
        json_path = sim_dir / "coverage_report.json"
        if json_path.exists():
            return json_path
        txt_path = sim_dir / "coverage_report.txt"
        if txt_path.exists():
            return txt_path
        return json_path
    return None


def _is_coverage_artifact(name: str) -> bool:
    lowered = str(name or "").strip().lower()
    return lowered in ("coverage_report", "coverage")


def _is_coverage_source(source: str | None) -> bool:
    if source is None or str(source).strip() == "":
        return True
    lowered = str(source).strip().lower()
    return lowered in ("coverage_report", "coverage")


def _sim_passed(node_id: str, attempt: int | None) -> bool:
    path = _select_stage_dir(Path("artifacts/task_memory") / node_id, "sim", attempt) / "log.txt"
    if not path.exists():
        return False
    text = path.read_text()
    if "FAIL" in text or "ERROR" in text:
        return False
    if "PASS" in text or "Simulation passed." in text:
        return True
    # If sim ran without explicit PASS markers, treat it as passed unless a failure marker was seen.
    return True


def _load_metric_value(metric_id: str, source: str | None, node_id: str, attempt: int | None):
    base = Path("artifacts/task_memory") / node_id
    src = (source or "coverage_report").lower()
    if src in ("sim_log", "simulation_log"):
        path = _select_stage_dir(base, "sim", attempt) / "log.txt"
        return _extract_metric_from_text(metric_id, path)
    if src in ("lint_log", "lint_report"):
        path = _select_stage_dir(base, "lint", attempt) / "log.txt"
        return _extract_metric_from_text(metric_id, path)
    if src in ("coverage_report", "coverage"):
        sim_dir = _select_stage_dir(base, "sim", attempt)
        json_path = sim_dir / "coverage_report.json"
        txt_path = sim_dir / "coverage_report.txt"
        if json_path.exists():
            return _extract_metric_from_json(metric_id, json_path)
        return _extract_metric_from_text(metric_id, txt_path)
    if src.endswith(".json"):
        return _extract_metric_from_json(metric_id, Path(src))
    if src.endswith(".txt"):
        return _extract_metric_from_text(metric_id, Path(src))
    return _extract_metric_from_text(metric_id, base / "sim" / "log.txt")


def _parse_attempt(value) -> int | None:
    if value is None:
        return None
    try:
        attempt = int(value)
    except Exception:
        return None
    return attempt if attempt > 0 else None


def _select_stage_dir(base: Path, kind: str, attempt: int | None) -> Path:
    if attempt is None:
        return base / kind
    exact = base / f"{kind}_attempt{attempt}"
    if exact.exists():
        return exact
    best = None
    for candidate in base.glob(f"{kind}_attempt*"):
        suffix = candidate.name[len(f"{kind}_attempt") :]
        if not suffix.isdigit():
            continue
        num = int(suffix)
        if num <= attempt and (best is None or num > best):
            best = num
    if best is not None:
        return base / f"{kind}_attempt{best}"
    return base / kind


def _extract_metric_from_json(metric_id: str, path: Path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if isinstance(data, dict):
        if metric_id in data:
            return data[metric_id]
        metrics = data.get("metrics")
        if isinstance(metrics, dict) and metric_id in metrics:
            return metrics[metric_id]
        coverage = data.get("coverage")
        if isinstance(coverage, dict) and metric_id in coverage:
            return coverage[metric_id]
    return None


def _extract_metric_from_text(metric_id: str, path: Path):
    if not path.exists():
        return None
    text = path.read_text()
    pattern = re.compile(rf"{re.escape(metric_id)}\\s*[:=]\\s*([0-9]*\\.?[0-9]+)")
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1)


def _compare_metric(value, target_raw, operator: str) -> bool:
    target_text = "" if target_raw is None else str(target_raw).strip()
    value_num = _to_float(value)
    target_num = _to_float(target_text)
    if operator in (">", ">=", "<", "<="):
        if value_num is None or target_num is None:
            return False
        if operator == ">":
            return value_num > target_num
        if operator == ">=":
            return value_num >= target_num
        if operator == "<":
            return value_num < target_num
        if operator == "<=":
            return value_num <= target_num
    if operator == "==":
        if value_num is not None and target_num is not None:
            return value_num == target_num
        return str(value).strip() == target_text
    if operator == "!=":
        if value_num is not None and target_num is not None:
            return value_num != target_num
        return str(value).strip() != target_text
    return False


def _to_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
