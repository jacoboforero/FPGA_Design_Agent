"""
Versatile CLI for running the end-to-end demo pipeline or individual steps.

Commands:
  plan            Generate design_context.json and dag.json (planner stub)
  run             Run full pipeline (plan -> start workers -> orchestrate)
  lint            Run lint on a given RTL file (uses lint worker logic)
  sim             Run simulation on RTL + testbench (uses sim worker logic)
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Iterable, List

import pika

# Agents
from agents.implementation.worker import ImplementationWorker
from agents.testbench.worker import TestbenchWorker
from agents.reflection.worker import ReflectionWorker
from agents.debug.worker import DebugWorker
from agents.spec_helper.worker import SpecHelperWorker

# Workers
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker
from workers.distill.worker import DistillWorker

# Orchestrator
from orchestrator.orchestrator_service import DemoOrchestrator
from orchestrator import planner_stub
from orchestrator import planner
from apps.cli import spec_flow

# Schema models
from core.schemas.contracts import TaskMessage, EntityType, WorkerType

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def cmd_plan(args: argparse.Namespace) -> None:
    # Prefer real specs; fallback to stub if not locked or flag set.
    use_stub = args.stub
    if not use_stub:
        try:
            planner.generate_from_specs()
            print("Generated design_context.json and dag.json from locked specs.")
            return
        except Exception as exc:  # noqa: BLE001
            if not args.allow_stub:
                raise
            print(f"Spec-based planning failed ({exc}); falling back to stub.")
            use_stub = True
    planner_stub.generate()
    print("Generated design_context.json and dag.json via planner stub.")


def cmd_run(args: argparse.Namespace) -> None:
    # Ensure plan exists
    try:
        planner.generate_from_specs()
    except Exception:
        if args.allow_stub:
            planner_stub.generate()
            print("Using planner stub outputs (no locked specs found).")
        else:
            raise
    params = connection_params_from_env()
    stop_event = threading.Event()
    workers = start_workers(params, stop_event)
    try:
        design_context = REPO_ROOT / "artifacts" / "generated" / "design_context.json"
        dag_path = REPO_ROOT / "artifacts" / "generated" / "dag.json"
        rtl_root = REPO_ROOT / "artifacts" / "generated"
        task_memory_root = REPO_ROOT / "artifacts" / "task_memory"
        DemoOrchestrator(params, design_context, dag_path, rtl_root, task_memory_root).run(timeout_s=args.timeout)
    finally:
        stop_workers(workers, stop_event)


def cmd_lint(args: argparse.Namespace) -> None:
    rtl_path = Path(args.rtl).resolve()
    msg = TaskMessage(entity_type=EntityType.LIGHT_DETERMINISTIC, task_type=WorkerType.LINTER, context={"rtl_path": str(rtl_path)})
    worker = LintWorker(connection_params=None, stop_event=threading.Event())
    result = worker.handle_task(msg)
    print(result.status.value)
    print(result.log_output)


def cmd_sim(args: argparse.Namespace) -> None:
    rtl_path = Path(args.rtl).resolve()
    tb_path = Path(args.testbench).resolve() if args.testbench else None
    ctx = {"rtl_path": str(rtl_path)}
    if tb_path:
        ctx["tb_path"] = str(tb_path)
    msg = TaskMessage(entity_type=EntityType.HEAVY_DETERMINISTIC, task_type=WorkerType.SIMULATOR, context=ctx)
    worker = SimulationWorker(connection_params=None, stop_event=threading.Event())
    result = worker.handle_task(msg)
    print(result.status.value)
    print(result.log_output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hardware agent system CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Generate design_context.json and dag.json (from specs if locked, else stub with --stub or --allow-stub)")
    p_plan.add_argument("--stub", action="store_true", help="Force use of planner stub instead of locked specs")
    p_plan.add_argument("--allow-stub", action="store_true", help="If spec planning fails, fall back to stub")
    p_plan.set_defaults(func=cmd_plan)

    p_run = sub.add_parser("run", help="Run full pipeline (plan + workers + orchestrator)")
    p_run.add_argument("--timeout", type=float, default=120.0, help="Pipeline timeout in seconds")
    p_run.add_argument("--allow-stub", action="store_true", help="Allow stub planner if specs are not locked")
    p_run.set_defaults(func=cmd_run)

    p_lint = sub.add_parser("lint", help="Run lint on RTL file")
    p_lint.add_argument("--rtl", required=True, help="Path to RTL file")
    p_lint.set_defaults(func=cmd_lint)

    p_sim = sub.add_parser("sim", help="Run simulation on RTL (+ optional testbench)")
    p_sim.add_argument("--rtl", required=True, help="Path to RTL file")
    p_sim.add_argument("--testbench", help="Path to testbench file")
    p_sim.set_defaults(func=cmd_sim)

    p_spec = sub.add_parser("spec", help="Interactive spec helper to collect and lock L1–L5")
    p_spec.set_defaults(func=lambda args: spec_flow.collect_specs())

    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
