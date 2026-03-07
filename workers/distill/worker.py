"""
Distillation worker: consumes process_tasks and distills simulation logs.
Fails hard if upstream logs are missing.
"""
from __future__ import annotations

import json
import re
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import pika
from core.schemas.contracts import DistilledDataset, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_max_retries, get_retry_count, next_retry_headers
from core.runtime.broker import DEFAULT_RESULTS_ROUTING_KEY, TASK_EXCHANGE, resolve_task_queue
from core.runtime.config import get_runtime_config


class DistillWorker(threading.Thread):
    queue_name = resolve_task_queue("DistillationWorker") or "process_tasks"

    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self.worker_instance_id = f"worker_distill:{id(self):x}"

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
                # Only handle distillation tasks (skip others)
                if task.task_type.value != "DistillationWorker":
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                received_at = datetime.now(timezone.utc)
                emit_runtime_event(
                    runtime="worker_distill",
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
                        log_output=f"Unhandled distillation error: {exc}",
                    )
                result = result.model_copy(
                    update={
                        "received_at": result.received_at or received_at,
                        "started_at": result.started_at or received_at,
                    }
                )
                self._publish_result(ch, task, result)
                emit_runtime_event(
                    runtime="worker_distill",
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
        node_id = task.context.get("node_id")
        if not node_id:
            raise TaskInputError("Missing node_id in task context.")
        attempt = _parse_attempt(task.context.get("attempt"))
        sim_log = Path("artifacts/task_memory") / node_id / _stage_dir("sim", attempt) / "log.txt"
        if not sim_log.exists():
            raise TaskInputError(f"Missing simulation log for distillation: {sim_log}")

        sim_text = sim_log.read_text()
        original_size = len(sim_text.encode())
        cycle, time_val = _extract_failure_info(sim_text)
        window = None
        if cycle is not None:
            sim_cfg = get_runtime_config().sim
            before = int(sim_cfg.fail_window_before)
            after = int(sim_cfg.fail_window_after)
            window = {"start_cycle": max(0, cycle - before), "end_cycle": cycle + after}
        fail_line_idx, fail_line = _extract_failure_line(sim_text)
        failure_signal_snapshot = _extract_failure_signal_snapshot(fail_line)
        log_excerpt = _extract_log_excerpt(sim_text, fail_line_idx)
        signal_hints = _extract_signal_hints(sim_text, fail_line_idx)
        waveform_path = Path("artifacts/task_memory") / node_id / _stage_dir("sim", attempt) / "waveform.vcd"
        waveform_present = waveform_path.exists()
        waveform_str = str(waveform_path) if waveform_present else None
        waveform_excerpt = None
        if waveform_present:
            waveform_excerpt = _distill_waveform_excerpt(
                vcd_path=waveform_path,
                failure_time=time_val,
                failure_cycle=cycle,
                cycle_window=window,
                signal_hints=signal_hints,
            )
        waveform_failure_snapshot = _extract_waveform_failure_snapshot(waveform_excerpt, signal_hints)
        distilled_path = Path("artifacts/task_memory") / node_id / _stage_dir("distill", attempt) / "distilled_dataset.json"
        distilled_path.parent.mkdir(parents=True, exist_ok=True)
        distilled_payload = {
            "node_id": node_id,
            "attempt": attempt,
            "failure_cycle": cycle,
            "failure_time": time_val,
            "failure_window": window,
            "failure_line_index": fail_line_idx,
            "failure_line": fail_line,
            "failure_signal_snapshot": failure_signal_snapshot,
            "log_excerpt": log_excerpt,
            "log_length": original_size,
            "waveform_path": waveform_str,
            "signal_hints": signal_hints,
            "waveform_excerpt": waveform_excerpt,
            "waveform_failure_snapshot": waveform_failure_snapshot,
        }
        distilled_path.write_text(json.dumps(distilled_payload, indent=2))
        distilled_size = len(distilled_path.read_bytes())
        compression_ratio = original_size / distilled_size if distilled_size else 0.0

        failure_focus = ["sim_log"]
        if waveform_present:
            failure_focus.append("waveform")
        dataset = DistilledDataset(
            original_data_size=original_size,
            distilled_data_size=distilled_size,
            compression_ratio=compression_ratio,
            failure_focus_areas=failure_focus,
            data_path=str(distilled_path),
        )
        emit_runtime_event(
            runtime="worker_distill",
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "dataset": dataset.data_path},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            log_output=_distill_log(cycle, time_val, window, waveform_str),
            distilled_dataset=dataset,
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


_FAIL_CYCLE_RE = re.compile(r"\bcycle\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_TIME_RE = re.compile(r"\btime\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_LINE_RE = re.compile(r"\b(FAIL|ERROR)\b", re.IGNORECASE)
_SIGNAL_HINT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=")
_FAIL_KV_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z0-9_xXzZ']+)")

_DEFAULT_SIGNAL_HINTS = {
    "clk",
    "clock",
    "rst",
    "rst_n",
    "reset",
    "reset_n",
    "en",
    "load",
    "load_value",
    "saturate",
    "count",
    "rollover",
}


def _extract_failure_info(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    lines = text.splitlines()
    candidates = [line for line in lines if "FAIL" in line or "ERROR" in line]
    if not candidates:
        candidates = lines
    cycle = None
    time_val = None
    for line in candidates:
        if cycle is None:
            match = _FAIL_CYCLE_RE.search(line)
            if match:
                cycle = int(match.group(1))
        if time_val is None:
            match = _FAIL_TIME_RE.search(line)
            if match:
                time_val = int(match.group(1))
        if cycle is not None or time_val is not None:
            break
    return cycle, time_val


def _extract_failure_line(text: str | None) -> tuple[int | None, str | None]:
    if not text:
        return None, None
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if _FAIL_LINE_RE.search(line):
            return idx, line
    return None, None


def _extract_failure_signal_snapshot(fail_line: str | None) -> dict[str, str]:
    if not fail_line:
        return {}
    snapshot: dict[str, str] = {}
    for key, value in _FAIL_KV_RE.findall(fail_line):
        snapshot[key] = value
    return snapshot


def _extract_log_excerpt(text: str | None, fail_idx: int | None) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if not lines:
        return ""
    if fail_idx is None:
        excerpt_lines = lines[:40]
        return "\n".join(f"{i+1}: {line}" for i, line in enumerate(excerpt_lines))
    start = max(0, fail_idx - 20)
    end = min(len(lines), fail_idx + 21)
    return "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))


def _extract_signal_hints(text: str | None, fail_idx: int | None) -> list[str]:
    if not text:
        return sorted(_DEFAULT_SIGNAL_HINTS)
    lines = text.splitlines()
    candidates: list[str] = []
    if fail_idx is not None and 0 <= fail_idx < len(lines):
        candidates.append(lines[fail_idx])
    candidates += [line for line in lines if _FAIL_LINE_RE.search(line)]
    hints: set[str] = set()
    for line in candidates:
        for match in _SIGNAL_HINT_RE.finditer(line):
            hints.add(match.group(1))
    if not hints:
        hints = set(_DEFAULT_SIGNAL_HINTS)
    else:
        hints |= _DEFAULT_SIGNAL_HINTS
    return sorted(hints)


def _distill_waveform_excerpt(
    *,
    vcd_path: Path,
    failure_time: int | None,
    failure_cycle: int | None,
    cycle_window: dict | None,
    signal_hints: list[str],
) -> dict | None:
    try:
        hints_lower = {h.lower() for h in signal_hints}
        sim_cfg = get_runtime_config().sim
        max_signals = int(sim_cfg.vcd_max_signals)
        max_changes = int(sim_cfg.vcd_max_changes_per_signal)
        before_time = int(sim_cfg.vcd_time_window_before)
        after_time = int(sim_cfg.vcd_time_window_after)

        start_time = 0
        end_time = 0
        if failure_time is not None:
            start_time = max(0, failure_time - before_time)
            end_time = failure_time + after_time
        elif failure_cycle is not None and cycle_window is not None:
            start_time = max(0, (cycle_window.get("start_cycle", 0)) * before_time)
            end_time = (cycle_window.get("end_cycle", 0)) * after_time
        else:
            end_time = before_time + after_time

        id_to_name: dict[str, str] = {}
        id_to_leaf: dict[str, str] = {}
        id_to_leaf_base: dict[str, str] = {}
        scope_stack: list[str] = []
        with vcd_path.open() as handle:
            for raw in handle:
                line = raw.strip()
                if line.startswith("$scope"):
                    parts = line.split()
                    if len(parts) >= 3:
                        scope_stack.append(parts[2])
                elif line.startswith("$upscope"):
                    if scope_stack:
                        scope_stack.pop()
                elif line.startswith("$var"):
                    parts = line.split()
                    if len(parts) >= 5:
                        var_id = parts[3]
                        ref = parts[4]
                        full = ".".join(scope_stack + [ref]) if scope_stack else ref
                        id_to_name[var_id] = full
                        id_to_leaf[var_id] = ref
                        id_to_leaf_base[var_id] = ref.split("[", 1)[0]
                elif line.startswith("$enddefinitions"):
                    break

        selected_ids = []
        for var_id, leaf in id_to_leaf.items():
            leaf_base = id_to_leaf_base.get(var_id, leaf)
            leaf_lower = leaf.lower()
            base_lower = leaf_base.lower()
            if leaf_lower in hints_lower:
                selected_ids.append(var_id)
            elif base_lower in hints_lower:
                selected_ids.append(var_id)
            elif leaf_lower in _DEFAULT_SIGNAL_HINTS or base_lower in _DEFAULT_SIGNAL_HINTS:
                selected_ids.append(var_id)
        # Deduplicate and cap
        seen_ids = set()
        ordered_ids: list[str] = []
        for var_id in selected_ids:
            if var_id in seen_ids:
                continue
            seen_ids.add(var_id)
            ordered_ids.append(var_id)
            if len(ordered_ids) >= max_signals:
                break

        if not ordered_ids:
            return {
                "time_window": {"start": start_time, "end": end_time},
                "selected_signals": [],
                "notes": "No matching signals found in VCD header for provided hints.",
            }

        changes: dict[str, deque] = {var_id: deque(maxlen=max_changes) for var_id in ordered_ids}
        initial_values: dict[str, str | None] = {var_id: None for var_id in ordered_ids}
        last_values: dict[str, str | None] = {var_id: None for var_id in ordered_ids}
        value_at_failure: dict[str, str | None] = {var_id: None for var_id in ordered_ids}
        pre_window_values: dict[str, str | None] = {var_id: None for var_id in ordered_ids}
        pre_window_transition: dict[str, tuple[int, str] | None] = {var_id: None for var_id in ordered_ids}
        truncated: dict[str, bool] = {var_id: False for var_id in ordered_ids}

        current_time = None
        in_dumpvars = False
        with vcd_path.open() as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    try:
                        current_time = int(line[1:])
                    except ValueError:
                        continue
                    if current_time > end_time:
                        break
                    continue
                if line.startswith("$dumpvars"):
                    in_dumpvars = True
                    continue
                if in_dumpvars and line.startswith("$end"):
                    in_dumpvars = False
                    continue
                if line.startswith("$"):
                    continue

                if current_time is None:
                    continue

                value = None
                var_id = None
                if line[0] in "01xXzZ":
                    value = line[0]
                    var_id = line[1:].strip()
                elif line[0] in "bBrR":
                    parts = line.split()
                    if len(parts) >= 2:
                        value = parts[0][1:]
                        var_id = parts[1]
                if var_id is None or var_id not in changes:
                    continue

                last_values[var_id] = value
                if failure_time is not None and current_time <= failure_time:
                    value_at_failure[var_id] = value
                if current_time < start_time:
                    pre_window_values[var_id] = value
                    pre_window_transition[var_id] = (current_time, value)
                    continue
                if initial_values[var_id] is None:
                    initial_values[var_id] = value
                if len(changes[var_id]) >= max_changes:
                    truncated[var_id] = True
                    continue
                changes[var_id].append((current_time, value))

        selected_signals = []
        for var_id in ordered_ids:
            selected_signals.append(
                {
                    "name": id_to_name.get(var_id, var_id),
                    "id": var_id,
                    "initial_value": initial_values[var_id],
                    "pre_window_value": pre_window_values[var_id],
                    "pre_window_transition": pre_window_transition[var_id],
                    "value_at_failure_time": value_at_failure[var_id],
                    "last_value": last_values[var_id],
                    "changes": list(changes[var_id]),
                    "truncated": truncated[var_id],
                }
            )

        return {
            "time_window": {"start": start_time, "end": end_time},
            "failure_time": failure_time,
            "selected_signals": selected_signals,
            "selected_signal_count": len(selected_signals),
            "notes": "Includes pre-window transitions and value_at_failure_time to reduce stale-endpoint ambiguity.",
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"waveform excerpt failed: {exc}"}


def _extract_waveform_failure_snapshot(waveform_excerpt: dict | None, signal_hints: list[str]) -> dict[str, str]:
    if not isinstance(waveform_excerpt, dict):
        return {}
    selected = waveform_excerpt.get("selected_signals")
    if not isinstance(selected, list):
        return {}
    hints = {hint.lower() for hint in signal_hints}
    snapshot: dict[str, str] = {}
    for item in selected:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        leaf = name.split(".")[-1].split("[", 1)[0].lower()
        if hints and leaf not in hints:
            continue
        value = item.get("value_at_failure_time")
        if value is None:
            value = item.get("last_value")
        if value is None:
            continue
        snapshot[name] = str(value)
    return snapshot


def _distill_log(
    cycle: int | None,
    time_val: int | None,
    window: dict | None,
    waveform_path: str | None,
) -> str:
    parts = ["Distillation complete."]
    if cycle is not None or time_val is not None:
        cycle_msg = str(cycle) if cycle is not None else "unknown"
        time_msg = str(time_val) if time_val is not None else "unknown"
        parts.append(f"failure_cycle={cycle_msg} failure_time={time_msg}")
    if window:
        parts.append(f"window_cycles={window.get('start_cycle')}..{window.get('end_cycle')}")
    if waveform_path:
        parts.append(f"waveform_path={waveform_path}")
    else:
        parts.append("waveform_present=no")
    return " ".join(parts)


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
