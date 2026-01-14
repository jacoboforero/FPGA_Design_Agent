"""
Shared agent worker base for the REASONING runtime.
Each specialized agent worker subclasses this to service a subset of AgentType
tasks from the shared ``agent_tasks`` queue and emits results to ``RESULTS``.
"""
from __future__ import annotations

import threading
from typing import Iterable, Set

import pika
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_retry_count, next_retry_headers, MAX_RETRIES

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class AgentWorkerBase(threading.Thread):
    queue_name = "agent_tasks"
    handled_types: Set[AgentType] = set()
    runtime_name: str = "agent"

    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event

    def should_handle(self, task: TaskMessage) -> bool:
        try:
            agent_type = AgentType(task.task_type.value)
        except Exception:
            return False
        return agent_type in self.handled_types

    def handle_task(self, task: TaskMessage) -> ResultMessage:  # pragma: no cover - overridden
        raise NotImplementedError

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )

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
                if not self.should_handle(task):
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    continue
                emit_runtime_event(
                    runtime=self.runtime_name,
                    event_type="task_received",
                    payload={"task_id": str(task.task_id), "agent": task.task_type.value},
                )
                try:
                    result = self.handle_task(task)
                except TaskInputError:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except RetryableError as exc:
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
                        log_output=f"Unhandled agent error: {exc}",
                    )
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)
