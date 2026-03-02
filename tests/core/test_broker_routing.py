from __future__ import annotations

from core.runtime.broker import resolve_task_queue, resolve_task_routing


def test_resolve_task_routing_prefers_task_specific_key():
    routing = resolve_task_routing("REASONING", "ImplementationAgent")
    assert routing == "task.agent.implementation"


def test_resolve_task_routing_falls_back_to_entity_key():
    routing = resolve_task_routing("LIGHT_DETERMINISTIC", "UnknownWorker")
    assert routing == "LIGHT_DETERMINISTIC"


def test_resolve_task_queue_returns_dedicated_queue_name():
    queue_name = resolve_task_queue("AcceptanceWorker")
    assert queue_name == "process_acceptance_tasks"

