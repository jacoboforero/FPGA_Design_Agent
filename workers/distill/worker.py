"""
Distillation worker: consumes process_tasks and distills simulation logs.
Fails hard if upstream logs are missing.
"""
from __future__ import annotations

import json
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
        sim_log = Path("artifacts/task_memory") / node_id / "sim" / "log.txt"
        if not sim_log.exists():
            raise TaskInputError(f"Missing simulation log for distillation: {sim_log}")

        sim_text = sim_log.read_text()
        original_size = len(sim_text.encode())
        distilled_path = Path("artifacts/task_memory") / node_id / "distill" / "distilled_dataset.json"
        distilled_path.parent.mkdir(parents=True, exist_ok=True)
        distilled_payload = {
            "node_id": node_id,
            "log_excerpt": "\n".join(sim_text.splitlines()[:40]),
            "log_length": original_size,
        }
        distilled_path.write_text(json.dumps(distilled_payload, indent=2))
        distilled_size = len(distilled_path.read_bytes())
        compression_ratio = original_size / distilled_size if distilled_size else 0.0

        dataset = DistilledDataset(
            original_data_size=original_size,
            distilled_data_size=distilled_size,
            compression_ratio=compression_ratio,
            failure_focus_areas=["sim_log"],
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
            log_output="Distillation complete.",
            distilled_dataset=dataset,
        )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
