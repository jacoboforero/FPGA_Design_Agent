"""
Simulation worker for demo. Consumes simulation_tasks and mocks a passing sim.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
import pika
from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class SimulationWorker(threading.Thread):
    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event

    def run(self) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.basic_qos(prefetch_count=1)
            for method, props, body in ch.consume("simulation_tasks", inactivity_timeout=0.5):
                if self.stop_event.is_set():
                    break
                if body is None:
                    continue
                task = TaskMessage.model_validate_json(body)
                result = self.handle_task(task)
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        # Try iverilog/vvp if available, else mock.
        iverilog = shutil.which("iverilog")
        vvp = shutil.which("vvp")
        rtl_path = task.context.get("rtl_path")
        tb_path = task.context.get("tb_path")
        if iverilog and vvp and rtl_path:
            try:
                sources = [rtl_path]
                if tb_path:
                    sources.append(tb_path)
                cmd = [iverilog, "-g2012", "-g2005-sv", "-o", "/tmp/sim.out", *sources]
                build = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if build.returncode != 0:
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=f"{' '.join(cmd)}\n{build.stderr or build.stdout}",
                    )
                run_cmd = [vvp, "/tmp/sim.out"]
                run = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
                if run.returncode != 0:
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=f"{' '.join(run_cmd)}\n{run.stderr or run.stdout}",
                    )
                emit_runtime_event(
                    runtime="worker_sim",
                    event_type="task_completed",
                    payload={"task_id": str(task.task_id)},
                )
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.SUCCESS,
                    artifacts_path=None,
                    log_output=run.stdout or "Simulation passed.",
                )
            except Exception as exc:  # noqa: BLE001
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=None,
                    log_output=f"Simulation failed: {exc}",
                )

        # Mock coverage if tools absent
        time.sleep(0.05)
        emit_runtime_event(
            runtime="worker_sim",
            event_type="task_completed",
            payload={"task_id": str(task.task_id)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=None,
            log_output="Mock simulation passed with coverage.",
        )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
