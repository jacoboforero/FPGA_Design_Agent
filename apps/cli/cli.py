"""
CLI entrypoint for the end-to-end pipeline and benchmark runner.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urlparse

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
from workers.acceptance.worker import AcceptanceWorker
from workers.tb_lint.worker import TestbenchLintWorker
from workers.sim.worker import SimulationWorker
from workers.distill.worker import DistillWorker

# Orchestrator
from orchestrator.orchestrator_service import DemoOrchestrator
from apps.cli import spec_flow
from apps.cli.execution_narrator import ExecutionNarrator, NarratorDispatcher

# Schema models
from core.observability.setup import configure_observability
from core.observability.agentops_tracker import get_tracker
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus
from core.runtime.broker import (
    TASK_EXCHANGE,
    RunRouting,
    create_run_routing,
    declare_results_queue,
    declare_task_topology,
    resolve_task_routing,
)
from core.runtime.config import DEFAULT_CONFIG_PATH, get_runtime_config, initialize_runtime_config


REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_BROKER_HOSTS = {"localhost", "127.0.0.1", "::1"}


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


def connection_params_from_config() -> pika.ConnectionParameters:
    broker_cfg = get_runtime_config().broker
    broker_url = _resolve_broker_url(broker_cfg.url)
    params = pika.URLParameters(broker_url)
    params.heartbeat = int(broker_cfg.heartbeat)
    params.blocked_connection_timeout = float(broker_cfg.blocked_connection_timeout)
    params.connection_attempts = int(broker_cfg.connection_attempts)
    params.retry_delay = float(broker_cfg.retry_delay)
    params.socket_timeout = float(broker_cfg.socket_timeout)
    return params


def _resolve_broker_url(configured_url: str) -> str:
    """
    YAML config is the source of truth, but keep a compatibility fallback:
    when config points to localhost and env points to a non-local host (e.g. docker service),
    prefer env so `make cli` works inside containers.
    """
    env_url = os.getenv("RABBITMQ_URL", "").strip()
    if not env_url:
        return configured_url
    cfg_host = (urlparse(configured_url).hostname or "").strip().lower()
    env_host = (urlparse(env_url).hostname or "").strip().lower()
    if cfg_host in _LOCAL_BROKER_HOSTS and env_host and env_host not in _LOCAL_BROKER_HOSTS:
        return env_url
    return configured_url


# Backwards-compatible import surface used by run_suite.
connection_params_from_env = connection_params_from_config


def _purge_broker_queues(params: pika.ConnectionParameters) -> None:
    if not get_runtime_config().broker.purge_queues_on_start:
        return
    queues = (
        "agent_tasks",
        "process_tasks",
        "simulation_tasks",
        "agent_planner_tasks",
        "agent_impl_tasks",
        "agent_tb_tasks",
        "agent_reflect_tasks",
        "agent_debug_tasks",
        "agent_spec_helper_tasks",
        "process_lint_tasks",
        "process_tb_lint_tasks",
        "process_acceptance_tasks",
        "process_distill_tasks",
        "results",
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        try:
            declare_task_topology(ch, include_legacy_bindings=True)
        except Exception:
            pass
        for queue_name in queues:
            try:
                ch.queue_purge(queue=queue_name)
            except Exception:
                continue


def start_workers(params: pika.ConnectionParameters, stop_event: threading.Event) -> List[threading.Thread]:
    cfg = get_runtime_config()
    pool = cfg.workers.pool_sizes
    worker_specs = [
        (ImplementationWorker, int(pool.implementation)),
        (TestbenchWorker, int(pool.testbench)),
        (ReflectionWorker, int(pool.reflection)),
        (DebugWorker, int(pool.debug)),
        (SpecHelperWorker, int(pool.spec_helper)),
        (LintWorker, int(pool.lint)),
        (TestbenchLintWorker, int(pool.tb_lint)),
        (AcceptanceWorker, int(pool.acceptance)),
        (DistillWorker, int(pool.distill)),
        (SimulationWorker, int(pool.simulation)),
    ]
    workers: List[threading.Thread] = []
    for worker_cls, count in worker_specs:
        for _ in range(max(1, count)):
            workers.append(worker_cls(params, stop_event))

    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        declare_task_topology(ch, include_legacy_bindings=True)

    for w in workers:
        w.start()
    return workers


def stop_workers(workers: Iterable[threading.Thread], stop_event: threading.Event) -> None:
    stop_event.set()
    for w in workers:
        while w.is_alive():
            w.join(timeout=0.5)


def _run_planner_task(
    params: pika.ConnectionParameters,
    run_routing: RunRouting,
    *,
    timeout: float = 30.0,
    execution_policy: dict | None = None,
) -> None:
    if timeout <= 0:
        timeout = float("inf")
    task_ctx = {
        "spec_dir": str(REPO_ROOT / "artifacts" / "task_memory" / "specs"),
        "out_dir": str(REPO_ROOT / "artifacts" / "generated"),
    }
    if execution_policy:
        task_ctx["execution_policy"] = execution_policy
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.PLANNER,
        context=task_ctx,
        run_id=run_routing.run_id,
        results_routing_key=run_routing.results_routing_key,
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        declare_task_topology(ch, include_legacy_bindings=True)
        results_queue = declare_results_queue(
            ch,
            results_routing_key=run_routing.results_routing_key,
        )
        routing_key = resolve_task_routing(task.entity_type.value, task.task_type.value)
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=routing_key,
            body=task.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
        start = datetime.now(timezone.utc)
        while (datetime.now(timezone.utc) - start).total_seconds() < timeout:
            method, props, body = ch.basic_get(queue=results_queue, auto_ack=False)
            if body is None:
                time.sleep(0.05)
                continue
            result = ResultMessage.model_validate_json(body)
            if result.task_id != task.task_id:
                ch.basic_nack(method.delivery_tag, requeue=True)
                continue
            ch.basic_ack(method.delivery_tag)
            if result.status is not TaskStatus.SUCCESS:
                raise RuntimeError(f"Planning failed: {result.log_output}")
            return
    raise RuntimeError("Planner timed out waiting for results. Verify broker queues are clean and planner worker is running.")


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


def _sanitize_module_hint(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"mod_{cleaned}"
    return cleaned


def _print_section(title: str) -> None:
    bar = "=" * len(title)
    print(f"\n{title}\n{bar}")


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{exc.__class__.__name__}: {exc!r}"


def _purge_task_memory(root: Path) -> None:
    if not root.exists():
        return
    shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def run_full(args: argparse.Namespace) -> None:
    cfg = get_runtime_config()
    preset = cfg.resolved_preset
    if preset.benchmark_mode:
        raise RuntimeError(
            "Benchmark preset uses official VerilogEval harness scoring. "
            "Run `python apps/cli/cli.py benchmark --preset benchmark` instead of full interactive mode."
        )
    execution_policy = {
        "preset": cfg.active_preset,
        "spec_profile": preset.spec_profile,
        "verification_profile": preset.verification_profile,
        "allow_repair_loop": preset.allow_repair_loop,
        "benchmark_mode": preset.benchmark_mode,
        "debug_max_retries": cfg.debug.max_retries,
    }

    run_name = args.run_name or _default_run_name("cli_full")
    execution_policy["run_name"] = run_name
    _purge_task_memory(REPO_ROOT / "artifacts" / "task_memory")
    configure_observability(run_name=run_name, default_tags=["cli", "full", f"preset:{cfg.active_preset}"])
    # 1) Collect specs interactively
    if args.direct_spec and not args.spec_file:
        raise RuntimeError("--direct-spec requires --spec-file.")
    if args.spec_file:
        spec_file = Path(args.spec_file).expanduser().resolve()
        if not spec_file.exists() or not spec_file.is_file():
            raise RuntimeError(f"Spec file not found: {spec_file}")
        spec_text = spec_file.read_text()
        module_hint = _sanitize_module_hint(spec_file.stem)
        spec_flow.collect_specs_from_text(
            module_hint,
            spec_text,
            interactive=False,
            spec_profile=preset.spec_profile,
            direct_parse=bool(args.direct_spec),
        )
    else:
        spec_flow.collect_specs()

    # 2) Plan
    _print_section("Planning")
    params = connection_params_from_config()
    _purge_broker_queues(params)
    planner_timeout = args.timeout if args.timeout > 0 else float(cfg.broker.planner_timeout_s)
    planner_stop = threading.Event()
    planner_worker = PlannerWorker(params, planner_stop)
    planner_worker.start()
    run_routing = create_run_routing()
    try:
        _run_planner_task(
            params,
            run_routing,
            timeout=planner_timeout,
            execution_policy=execution_policy,
        )
    finally:
        planner_stop.set()
        planner_worker.join(timeout=1.0)
    design_context = REPO_ROOT / "artifacts" / "generated" / "design_context.json"
    dag_path = REPO_ROOT / "artifacts" / "generated" / "dag.json"
    dag = json.loads(dag_path.read_text())
    nodes = ", ".join(n["id"] for n in dag.get("nodes", []))
    print(f"Plan generated: {dag_path} (nodes: {nodes})")

    if not args.yes and not _confirm("Proceed to execution?", True):
        print("Aborted after planning.")
        return

    # 3) Execute
    _print_section("Execution")
    rtl_root = REPO_ROOT / "artifacts" / "generated"
    task_memory_root = REPO_ROOT / "artifacts" / "task_memory"
    narrative_mode = args.narrative_mode or cfg.cli.default_narrative_mode
    narrator = None
    narrator_dispatcher = None
    if narrative_mode != "off":
        narrator = ExecutionNarrator(task_memory_root=task_memory_root, mode=narrative_mode)
        narrator_dispatcher = NarratorDispatcher(
            narrator,
            async_enabled=bool(cfg.cli.execution_narrator_async),
            order_mode=str(cfg.cli.execution_narrator_order_mode),
            queue_max_events=int(cfg.cli.execution_narrator_queue_max_events),
        )
        print(f"Narrative output enabled ({narrative_mode}).")
    stop_event = threading.Event()
    workers = start_workers(params, stop_event)
    try:
        DemoOrchestrator(
            params,
            design_context,
            dag_path,
            rtl_root,
            task_memory_root,
            event_callback=(narrator_dispatcher.emit if narrator_dispatcher else (narrator.handle_event if narrator else None)),
            raw_progress=narrative_mode == "off",
            run_id=run_routing.run_id,
            results_routing_key=run_routing.results_routing_key,
            allow_repair_loop=preset.allow_repair_loop,
            execution_policy=execution_policy,
        ).run(timeout_s=args.timeout)
    finally:
        stop_workers(workers, stop_event)
        if narrator_dispatcher is not None:
            narrator_dispatcher.close()
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
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to runtime YAML config.")
    parser.add_argument("--preset", help="Override active preset from config.")
    parser.add_argument("--timeout", type=float, default=0.0, help="Pipeline timeout in seconds (0 disables)")
    parser.add_argument("--run-name", help="Optional run name for observability/AgentOps")
    parser.add_argument("--spec-file", help="Path to a spec text file to run non-interactively.")
    parser.add_argument(
        "--direct-spec",
        action="store_true",
        help="Parse L1-L5 structured spec text directly (skip Spec Helper LLM interaction). Requires --spec-file.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt after planning.")
    parser.add_argument(
        "--narrative-mode",
        choices=("llm", "deterministic", "off"),
        default=None,
        help="Execution output mode: LLM narrative, deterministic narrative, or raw internal progress.",
    )
    return parser


def _run_benchmark_command(argv: list[str]) -> None:
    from apps.cli.run_verilog_eval import build_parser as build_benchmark_parser, run_from_args

    parser = build_benchmark_parser()
    args = parser.parse_args(argv)
    initialize_runtime_config(Path(args.config), preset_override=args.preset)
    run_from_args(args)


def _run_doctor_command(argv: list[str]) -> int:
    from apps.cli.doctor import build_parser as build_doctor_parser, run_from_args

    parser = build_doctor_parser()
    args = parser.parse_args(argv)
    initialize_runtime_config(Path(args.config), preset_override=args.preset)
    return int(run_from_args(args))


def main(argv: list[str] | None = None) -> None:
    _load_env_file(REPO_ROOT / ".env")
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "doctor":
        try:
            code = _run_doctor_command(argv[1:])
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(1)
        except Exception as exc:  # noqa: BLE001
            print(f"\nError: {_format_exception(exc)}")
            if os.getenv("CLI_SHOW_TRACEBACK") == "1":
                traceback.print_exc()
            sys.exit(1)
        if code != 0:
            sys.exit(code)
        return
    if argv and argv[0] == "benchmark":
        try:
            _run_benchmark_command(argv[1:])
        except KeyboardInterrupt:
            print("\nAborted.")
        except Exception as exc:  # noqa: BLE001
            print(f"\nError: {_format_exception(exc)}")
            if os.getenv("CLI_SHOW_TRACEBACK") == "1":
                traceback.print_exc()
            sys.exit(1)
        return
    if argv and argv[0] in ("run", "full"):
        argv = argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    initialize_runtime_config(Path(args.config), preset_override=args.preset)
    try:
        run_full(args)
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as exc:  # noqa: BLE001
        print(f"\nError: {_format_exception(exc)}")
        if os.getenv("CLI_SHOW_TRACEBACK") == "1":
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
