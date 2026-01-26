"""
Distillation worker: consumes process_tasks and distills simulation logs.
Fails hard if upstream logs are missing.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import pika
from core.schemas.contracts import DistilledDataset, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_retry_count, next_retry_headers, MAX_RETRIES

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class DistillWorker(threading.Thread):
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
                # Only handle distillation tasks (skip others)
                if task.task_type.value != "DistillationWorker":
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
                        log_output=f"Unhandled distillation error: {exc}",
                    )
                self._publish_result(ch, result)
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
            before = int(os.getenv("SIM_FAIL_WINDOW_BEFORE", "20"))
            after = int(os.getenv("SIM_FAIL_WINDOW_AFTER", "5"))
            window = {"start_cycle": max(0, cycle - before), "end_cycle": cycle + after}
        waveform_path = Path("artifacts/task_memory") / node_id / _stage_dir("sim", attempt) / "waveform.vcd"
        waveform_present = waveform_path.exists()
        waveform_str = str(waveform_path) if waveform_present else None
        distilled_path = Path("artifacts/task_memory") / node_id / _stage_dir("distill", attempt) / "distilled_dataset.json"
        distilled_path.parent.mkdir(parents=True, exist_ok=True)
        distilled_payload = {
            "node_id": node_id,
            "attempt": attempt,
            "failure_cycle": cycle,
            "failure_time": time_val,
            "failure_window": window,
            "log_excerpt": "\n".join(sim_text.splitlines()[:40]),
            "log_length": original_size,
            "waveform_path": waveform_str,
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

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


_FAIL_CYCLE_RE = re.compile(r"\bcycle\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_TIME_RE = re.compile(r"\btime\b\s*=?\s*(\d+)", re.IGNORECASE)


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
