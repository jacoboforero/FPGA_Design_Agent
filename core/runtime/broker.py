"""
Broker helpers for run-scoped result routing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
from uuid import uuid4

import pika


TASK_EXCHANGE = "tasks_exchange"
TASK_DLX = "tasks_dlx"
DEFAULT_RESULTS_ROUTING_KEY = "RESULTS"

LEGACY_AGENT_QUEUE = "agent_tasks"
LEGACY_PROCESS_QUEUE = "process_tasks"
LEGACY_SIM_QUEUE = "simulation_tasks"

TASK_ROUTING_BY_TASK_TYPE: Dict[str, str] = {
    "PlannerAgent": "task.agent.planner",
    "ImplementationAgent": "task.agent.implementation",
    "TestbenchAgent": "task.agent.testbench",
    "ReflectionAgent": "task.agent.reflection",
    "DebugAgent": "task.agent.debug",
    "SpecificationHelperAgent": "task.agent.spec_helper",
    "LinterWorker": "task.process.lint",
    "TestbenchLinterWorker": "task.process.tb_lint",
    "AcceptanceWorker": "task.process.acceptance",
    "DistillationWorker": "task.process.distill",
    "SimulatorWorker": "task.process.simulation",
}

TASK_QUEUE_BY_TASK_TYPE: Dict[str, str] = {
    "PlannerAgent": "agent_planner_tasks",
    "ImplementationAgent": "agent_impl_tasks",
    "TestbenchAgent": "agent_tb_tasks",
    "ReflectionAgent": "agent_reflect_tasks",
    "DebugAgent": "agent_debug_tasks",
    "SpecificationHelperAgent": "agent_spec_helper_tasks",
    "LinterWorker": "process_lint_tasks",
    "TestbenchLinterWorker": "process_tb_lint_tasks",
    "AcceptanceWorker": "process_acceptance_tasks",
    "DistillationWorker": "process_distill_tasks",
    "SimulatorWorker": "simulation_tasks",
}


def resolve_task_routing(entity_value: str, task_type_value: str) -> str:
    return TASK_ROUTING_BY_TASK_TYPE.get(task_type_value, entity_value)


def resolve_task_queue(task_type_value: str) -> str | None:
    return TASK_QUEUE_BY_TASK_TYPE.get(task_type_value)


def _declare_queue_with_dlx(
    ch: pika.adapters.blocking_connection.BlockingChannel,
    queue_name: str,
    *,
    with_priority: bool = False,
) -> None:
    args: Dict[str, object] = {"x-dead-letter-exchange": TASK_DLX}
    if with_priority:
        args["x-max-priority"] = 3
    ch.queue_declare(queue=queue_name, durable=True, auto_delete=False, arguments=args)


def declare_task_topology(
    ch: pika.adapters.blocking_connection.BlockingChannel,
    *,
    include_legacy_bindings: bool = True,
) -> None:
    # Ensure exchange + DLX exist for both direct routing and dead-letter handling.
    ch.exchange_declare(exchange=TASK_EXCHANGE, exchange_type="direct", durable=True)
    ch.exchange_declare(exchange=TASK_DLX, exchange_type="fanout", durable=True)

    # Dedicated per-task queues.
    for queue_name in sorted(set(TASK_QUEUE_BY_TASK_TYPE.values())):
        _declare_queue_with_dlx(ch, queue_name, with_priority=queue_name.startswith("agent_"))
    for task_type, routing_key in TASK_ROUTING_BY_TASK_TYPE.items():
        queue_name = TASK_QUEUE_BY_TASK_TYPE.get(task_type)
        if not queue_name:
            continue
        ch.queue_bind(queue=queue_name, exchange=TASK_EXCHANGE, routing_key=routing_key)

    # Migration compatibility: keep shared queues bound to coarse entity routing keys.
    if include_legacy_bindings:
        _declare_queue_with_dlx(ch, LEGACY_AGENT_QUEUE, with_priority=True)
        _declare_queue_with_dlx(ch, LEGACY_PROCESS_QUEUE, with_priority=False)
        _declare_queue_with_dlx(ch, LEGACY_SIM_QUEUE, with_priority=False)
        ch.queue_bind(queue=LEGACY_AGENT_QUEUE, exchange=TASK_EXCHANGE, routing_key="REASONING")
        ch.queue_bind(queue=LEGACY_PROCESS_QUEUE, exchange=TASK_EXCHANGE, routing_key="LIGHT_DETERMINISTIC")
        ch.queue_bind(queue=LEGACY_SIM_QUEUE, exchange=TASK_EXCHANGE, routing_key="HEAVY_DETERMINISTIC")


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
    "TASK_DLX",
    "DEFAULT_RESULTS_ROUTING_KEY",
    "TASK_ROUTING_BY_TASK_TYPE",
    "TASK_QUEUE_BY_TASK_TYPE",
    "resolve_task_routing",
    "resolve_task_queue",
    "declare_task_topology",
    "RunRouting",
    "create_run_routing",
    "declare_results_queue",
]
