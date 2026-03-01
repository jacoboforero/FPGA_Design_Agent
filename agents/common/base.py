"""
Shared agent worker base for the REASONING runtime.
Each specialized agent worker subclasses this to service a subset of AgentType
tasks from the shared ``agent_tasks`` queue and emits results to ``RESULTS``.
"""
from __future__ import annotations

import threading
import time
from typing import Iterable, Set

import pika
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_max_retries, get_retry_count, next_retry_headers
from core.runtime.broker import DEFAULT_RESULTS_ROUTING_KEY, TASK_EXCHANGE
from core.runtime.config import get_runtime_config


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

    def _publish_result(
        self,
        ch: pika.adapters.blocking_connection.BlockingChannel,
        task: TaskMessage,
        result: ResultMessage,
    ) -> None:
        routed = result.model_copy(update={"run_id": result.run_id or task.run_id})
        routing_key = task.results_routing_key or DEFAULT_RESULTS_ROUTING_KEY
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=routing_key,
            body=routed.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )

    def run(self) -> None:
        reconnect_delay_s = float(get_runtime_config().broker.reconnect_delay_s)
        while not self.stop_event.is_set():
            try:
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
                                log_output=f"Unhandled agent error: {exc}",
                            )
                        self._publish_result(ch, task, result)
                        ch.basic_ack(method.delivery_tag)
            except Exception as exc:  # noqa: BLE001
                emit_runtime_event(
                    runtime=self.runtime_name,
                    event_type="connection_error",
                    payload={"error": str(exc)},
                )
                if self.stop_event.is_set():
                    break
                time.sleep(reconnect_delay_s)
