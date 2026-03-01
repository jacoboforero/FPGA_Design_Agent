"""
Broker helpers for run-scoped result routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pika


TASK_EXCHANGE = "tasks_exchange"
DEFAULT_RESULTS_ROUTING_KEY = "RESULTS"


@dataclass(frozen=True)
class RunRouting:
    run_id: str
    results_routing_key: str


def create_run_routing(run_id: str | None = None) -> RunRouting:
    resolved = run_id or str(uuid4())
    return RunRouting(run_id=resolved, results_routing_key=f"{DEFAULT_RESULTS_ROUTING_KEY}.{resolved}")


def declare_results_queue(
    ch: pika.adapters.blocking_connection.BlockingChannel,
    *,
    results_routing_key: str,
    queue_name: str | None = None,
) -> str:
    # Run-isolated queue to avoid cross-run result consumption.
    resolved_queue = queue_name or ""
    declared = ch.queue_declare(queue=resolved_queue, durable=False, exclusive=True, auto_delete=True)
    queue = declared.method.queue
    ch.queue_bind(queue=queue, exchange=TASK_EXCHANGE, routing_key=results_routing_key)
    return queue


__all__ = [
    "TASK_EXCHANGE",
    "DEFAULT_RESULTS_ROUTING_KEY",
    "RunRouting",
    "create_run_routing",
    "declare_results_queue",
]
