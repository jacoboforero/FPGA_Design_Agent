"""
Deterministic lint worker for demo. Consumes process_tasks and performs mock lint.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

import pika
from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class LintWorker(threading.Thread):
    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self.verilator = shutil.which("verilator")

    def run(self) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.basic_qos(prefetch_count=1)
            for method, props, body in ch.consume("process_tasks", inactivity_timeout=0.5):
                if self.stop_event.is_set():
                    break
                if body is None:
                    continue
                task = TaskMessage.model_validate_json(body)
                # Skip non-lint tasks
                if task.task_type.value != "LinterWorker":
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    continue
                result = self.handle_task(task)
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        rtl_path = Path(task.context["rtl_path"])
        if not rtl_path.exists():
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"RTL missing: {rtl_path}",
            )

        if self.verilator:
            try:
                cmd = [self.verilator, "--lint-only", "--quiet", "--sv", str(rtl_path)]
                completed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if completed.returncode != 0:
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=completed.stderr or completed.stdout,
                    )
                log = completed.stdout or "Verilator lint passed."
            except Exception as exc:  # noqa: BLE001
                log = f"Verilator failed, falling back to mock: {exc}"
            else:
                emit_runtime_event(
                    runtime="worker_lint",
                    event_type="task_completed",
                    payload={"task_id": str(task.task_id), "artifacts_path": str(rtl_path)},
                )
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.SUCCESS,
                    artifacts_path=str(rtl_path),
                    log_output=log,
                )

        # Fallback mock lint
        contents = rtl_path.read_text()
        if "module" not in contents or "endmodule" not in contents:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="Missing module/endmodule.",
            )
        emit_runtime_event(
            runtime="worker_lint",
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "artifacts_path": str(rtl_path)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(rtl_path),
            log_output="Mock lint passed.",
        )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
