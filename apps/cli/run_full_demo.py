"""
Full demo runner:
- Uses locked specs to generate design context + DAG
- Launches agent runtimes (implementation/testbench/reflection/debug/spec helper) and deterministic workers (lint/sim/distill)
- Runs orchestrator to drive Implementation -> Lint -> Testbench -> Simulation -> Distill -> Reflection
Requires RabbitMQ running (docker-compose up -d in infrastructure) and toolchains installed.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pika

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.implementation.worker import ImplementationWorker
from agents.planner.worker import PlannerWorker
from agents.testbench.worker import TestbenchWorker
from agents.reflection.worker import ReflectionWorker
from agents.debug.worker import DebugWorker
from agents.spec_helper.worker import SpecHelperWorker
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker
from workers.distill.worker import DistillWorker
from orchestrator.orchestrator_service import DemoOrchestrator
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


def _run_planner_task(params, timeout: float = 30.0) -> None:
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.PLANNER,
        context={
            "spec_dir": str(REPO_ROOT / "artifacts" / "task_memory" / "specs"),
            "out_dir": str(REPO_ROOT / "artifacts" / "generated"),
        },
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        ch.queue_declare(queue="results", durable=True)
        ch.queue_bind(queue="results", exchange=TASK_EXCHANGE, routing_key=RESULTS_ROUTING_KEY)
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=task.entity_type.value,
            body=task.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
        start = time.time()
        while time.time() - start < timeout:
            method, props, body = ch.basic_get(queue="results", auto_ack=True)
            if body is None:
                continue
            result = ResultMessage.model_validate_json(body)
            if result.task_id != task.task_id:
                continue
            if result.status is not TaskStatus.SUCCESS:
                raise RuntimeError(result.log_output)
            return
    raise RuntimeError("Planner timed out waiting for results.")


def main() -> None:

    rabbit_url = os.getenv("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    try:
        params = pika.URLParameters(rabbit_url)
        conn = pika.BlockingConnection(params)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"RabbitMQ not reachable at {rabbit_url}. Start docker-compose in infrastructure/. Error: {exc}")
        return

    design_context = REPO_ROOT / "artifacts" / "generated" / "design_context.json"
    dag_path = REPO_ROOT / "artifacts" / "generated" / "dag.json"
    rtl_root = REPO_ROOT / "artifacts" / "generated"
    task_memory_root = REPO_ROOT / "artifacts" / "task_memory"

    stop_event = threading.Event()
    workers = [
        PlannerWorker(params, stop_event),
        ImplementationWorker(params, stop_event),
        TestbenchWorker(params, stop_event),
        ReflectionWorker(params, stop_event),
        DebugWorker(params, stop_event),
        SpecHelperWorker(params, stop_event),
        LintWorker(params, stop_event),
        DistillWorker(params, stop_event),
        SimulationWorker(params, stop_event),
    ]
    for w in workers:
        w.start()

    try:
        _run_planner_task(params, timeout=30.0)
        DemoOrchestrator(params, design_context, dag_path, rtl_root, task_memory_root).run()
    finally:
        stop_event.set()
        for w in workers:
            w.join(timeout=1.0)


if __name__ == "__main__":
    main()
