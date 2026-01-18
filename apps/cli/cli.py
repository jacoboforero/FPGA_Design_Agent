"""
Minimal CLI for the end-to-end demo pipeline (spec -> plan -> run).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

import pika

# Agents
from agents.implementation.worker import ImplementationWorker
from agents.testbench.worker import TestbenchWorker
from agents.reflection.worker import ReflectionWorker
from agents.debug.worker import DebugWorker
from agents.spec_helper.worker import SpecHelperWorker
from agents.planner.worker import PlannerWorker

# Workers
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker
from workers.distill.worker import DistillWorker

# Orchestrator
from orchestrator.orchestrator_service import DemoOrchestrator
from apps.cli import spec_flow

# Schema models
from core.observability.setup import configure_observability
from core.observability.agentops_tracker import get_tracker
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and value[0] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        else:
            value = value.split("#", 1)[0].rstrip()
        os.environ.setdefault(key, value)


def connection_params_from_env() -> pika.ConnectionParameters:
    rabbit_url = os.getenv("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    return pika.URLParameters(rabbit_url)


def start_workers(params: pika.ConnectionParameters, stop_event: threading.Event) -> List[threading.Thread]:
    workers: List[threading.Thread] = [
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
    return workers


def stop_workers(workers: Iterable[threading.Thread], stop_event: threading.Event) -> None:
    stop_event.set()
    for w in workers:
        w.join(timeout=1.0)


def _run_planner_task(params: pika.ConnectionParameters, timeout: float = 30.0) -> None:
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
        start = datetime.now(timezone.utc)
        while (datetime.now(timezone.utc) - start).total_seconds() < timeout:
            method, props, body = ch.basic_get(queue="results", auto_ack=True)
            if body is None:
                continue
            result = ResultMessage.model_validate_json(body)
            if result.task_id != task.task_id:
                continue
            if result.status is not TaskStatus.SUCCESS:
                raise RuntimeError(f"Planning failed: {result.log_output}")
            return
    raise RuntimeError("Planner timed out waiting for results.")

def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    val = input(f"{prompt}{suffix} ").strip().lower()
    if val in ("n", "no"):
        return False
    if val in ("y", "yes"):
        return True
    return default


def _default_run_name(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def _print_section(title: str) -> None:
    bar = "=" * len(title)
    print(f"\n{title}\n{bar}")


def run_full(args: argparse.Namespace) -> None:
    run_name = args.run_name or _default_run_name("cli_full")
    configure_observability(run_name=run_name, default_tags=["cli", "full"])
    # 1) Collect specs interactively
    spec_flow.collect_specs()

    # 2) Plan
    _print_section("Planning")
    params = connection_params_from_env()
    planner_stop = threading.Event()
    planner_worker = PlannerWorker(params, planner_stop)
    planner_worker.start()
    try:
        _run_planner_task(params, timeout=args.timeout)
    finally:
        planner_stop.set()
        planner_worker.join(timeout=1.0)
    design_context = REPO_ROOT / "artifacts" / "generated" / "design_context.json"
    dag_path = REPO_ROOT / "artifacts" / "generated" / "dag.json"
    dag = json.loads(dag_path.read_text())
    nodes = ", ".join(n["id"] for n in dag.get("nodes", []))
    print(f"Plan generated: {dag_path} (nodes: {nodes})")

    if not _confirm("Proceed to execution?", True):
        print("Aborted after planning.")
        return

    # 3) Execute
    _print_section("Execution")
    stop_event = threading.Event()
    workers = start_workers(params, stop_event)
    try:
        rtl_root = REPO_ROOT / "artifacts" / "generated"
        task_memory_root = REPO_ROOT / "artifacts" / "task_memory"
        DemoOrchestrator(params, design_context, dag_path, rtl_root, task_memory_root).run(timeout_s=args.timeout)
    finally:
        stop_workers(workers, stop_event)
        get_tracker().finalize()

    # 4) Show RTL paths and contents
    ctx = json.loads(design_context.read_text())
    for node_id, node in ctx.get("nodes", {}).items():
        rtl_rel = node.get("rtl_file")
        if not rtl_rel:
            continue
        rtl_path = (REPO_ROOT / "artifacts" / "generated" / rtl_rel).resolve()
        print(f"\n[{node_id}] RTL at: {rtl_path}")
        try:
            print(rtl_path.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"(Could not read RTL: {exc})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hardware agent system CLI")
    parser.add_argument("--timeout", type=float, default=120.0, help="Pipeline timeout in seconds")
    parser.add_argument("--run-name", help="Optional run name for observability/AgentOps")
    return parser


def main(argv: list[str] | None = None) -> None:
    _load_env_file(REPO_ROOT / ".env")
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] in ("run", "full"):
        argv = argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_full(args)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as exc:  # noqa: BLE001
        print(f"\nError: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
