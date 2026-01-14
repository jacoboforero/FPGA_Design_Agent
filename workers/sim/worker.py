"""
Simulation worker. Runs iverilog/vvp and fails hard if tools are missing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import pika
from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_retry_count, next_retry_headers, MAX_RETRIES

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
                try:
                    task = TaskMessage.model_validate_json(body)
                except Exception:
                    ch.basic_nack(method.delivery_tag, requeue=False)
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
                        log_output=f"Unhandled simulation error: {exc}",
                    )
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        iverilog = os.getenv("IVERILOG_PATH") or shutil.which("iverilog")
        vvp = os.getenv("VVP_PATH") or shutil.which("vvp")
        rtl_path = task.context.get("rtl_path")
        tb_path = task.context.get("tb_path")
        if not iverilog or not vvp:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="Simulation tools missing; set IVERILOG_PATH and VVP_PATH or install iverilog/vvp.",
            )
        if not rtl_path:
            raise TaskInputError("Missing rtl_path in task context.")
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
        except subprocess.TimeoutExpired as exc:
            raise RetryableError(f"Simulation timeout: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Simulation failed: {exc}",
            )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
