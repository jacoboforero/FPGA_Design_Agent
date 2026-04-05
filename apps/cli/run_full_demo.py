"""
Full demo runner for non-interactive local execution.
"""
from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
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
from agents.finalizer.worker import FinalizerWorker
from agents.spec_helper.worker import SpecHelperWorker
from workers.lint.worker import LintWorker
from workers.acceptance.worker import AcceptanceWorker
from workers.tb_lint.worker import TestbenchLintWorker
from workers.sim.worker import SimulationWorker
from workers.distill.worker import DistillWorker
from orchestrator.orchestrator_service import DemoOrchestrator
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus
from core.runtime.broker import TASK_EXCHANGE, create_run_routing, declare_results_queue
from core.runtime.config import get_runtime_config, initialize_runtime_config
from apps.cli.cli import _load_env_file, connection_params_from_config
from core.observability.setup import configure_observability
from core.observability.agentops_tracker import get_tracker
from core.runtime.paths import default_env_file


def _run_planner_task(
    params: pika.ConnectionParameters,
    run_id: str,
    results_routing_key: str,
    execution_policy: dict,
    timeout: float = 30.0,
) -> None:
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.PLANNER,
        context={
            "spec_dir": str(REPO_ROOT / "artifacts" / "task_memory" / "specs"),
            "out_dir": str(REPO_ROOT / "artifacts" / "generated"),
            "execution_policy": execution_policy,
        },
        run_id=run_id,
        results_routing_key=results_routing_key,
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        results_queue = declare_results_queue(ch, results_routing_key=results_routing_key)
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=task.entity_type.value,
            body=task.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
        start = time.time()
        while time.time() - start < timeout:
            method, props, body = ch.basic_get(queue=results_queue, auto_ack=False)
            if body is None:
                continue
            result = ResultMessage.model_validate_json(body)
            if result.task_id != task.task_id:
                ch.basic_nack(method.delivery_tag, requeue=True)
                continue
            ch.basic_ack(method.delivery_tag)
            if result.status is not TaskStatus.SUCCESS:
                raise RuntimeError(result.log_output)
            return
    raise RuntimeError("Planner timed out waiting for results.")


def main() -> None:
    env_file = default_env_file()
    if env_file is not None:
        _load_env_file(env_file)
    initialize_runtime_config(default_name="runtime.yaml")
    runtime_cfg = get_runtime_config()
    execution_policy = {
        "spec_profile": runtime_cfg.run.spec_profile.model_dump(mode="python"),
        "verification_profile": runtime_cfg.run.verification_profile,
        "run_kind": "engineer",
    }

    rabbit_url = runtime_cfg.broker.url
    try:
        params = connection_params_from_config()
        conn = pika.BlockingConnection(params)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"RabbitMQ not reachable at {rabbit_url}. Start docker-compose in infrastructure/. Error: {exc}")
        return

    design_context = REPO_ROOT / "artifacts" / "generated" / "design_context.json"
    dag_path = REPO_ROOT / "artifacts" / "generated" / "dag.json"
    rtl_root = REPO_ROOT / "artifacts" / "generated"
    task_memory_root = REPO_ROOT / "artifacts" / "task_memory"

    run_routing = create_run_routing()
    run_name = f"demo_full_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    execution_policy["run_name"] = run_name
    configure_observability(run_name=run_name, run_id=run_routing.run_id, default_tags=["demo", "full"])
    stop_event = threading.Event()
    workers = [
        PlannerWorker(params, stop_event),
        ImplementationWorker(params, stop_event),
        TestbenchWorker(params, stop_event),
        ReflectionWorker(params, stop_event),
        DebugWorker(params, stop_event),
        SpecHelperWorker(params, stop_event),
        LintWorker(params, stop_event),
        TestbenchLintWorker(params, stop_event),
        AcceptanceWorker(params, stop_event),
        DistillWorker(params, stop_event),
        SimulationWorker(params, stop_event),
    ]
    if int(runtime_cfg.workers.pool_sizes.finalizer) > 0:
        workers.append(FinalizerWorker(params, stop_event))
    for w in workers:
        w.start()

    try:
        _run_planner_task(
            params,
            run_routing.run_id,
            run_routing.results_routing_key,
            execution_policy,
            timeout=30.0,
        )
        DemoOrchestrator(
            params,
            design_context,
            dag_path,
            rtl_root,
            task_memory_root,
            run_id=run_routing.run_id,
            results_routing_key=run_routing.results_routing_key,
            execution_policy=execution_policy,
        ).run()
    finally:
        stop_event.set()
        for w in workers:
            w.join(timeout=1.0)
        get_tracker().finalize()


if __name__ == "__main__":
    main()
