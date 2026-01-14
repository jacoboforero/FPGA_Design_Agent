"""
Automated smoke suite for the CLI pipeline with increasing design complexity.
Non-interactive: feeds full specs, plans, runs the orchestrator, and reports outcomes.
"""
from __future__ import annotations

import argparse
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List

import pika

from apps.cli.cli import connection_params_from_env, start_workers, stop_workers
from apps.cli import spec_flow
from orchestrator.orchestrator_service import DemoOrchestrator
from core.observability.setup import configure_observability
from core.observability.agentops_tracker import get_tracker
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus
from agents.planner.worker import PlannerWorker

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_GEN = REPO_ROOT / "artifacts" / "generated"
SPEC_DIR = REPO_ROOT / "artifacts" / "task_memory" / "specs"


def clean_artifacts() -> None:
    shutil.rmtree(ARTIFACTS_GEN, ignore_errors=True)
    shutil.rmtree(SPEC_DIR, ignore_errors=True)


def run_planner_task(params, timeout: float) -> None:
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.PLANNER,
        context={
            "spec_dir": str(SPEC_DIR),
            "out_dir": str(ARTIFACTS_GEN),
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
                raise RuntimeError(f"Planning failed: {result.log_output}")
            return
    raise RuntimeError("Planner timed out waiting for results.")


SUITE: List[Dict[str, str]] = [
    {
        "name": "and2",
        "spec": """Module: and2
1-bit combinational AND gate.
Signals:
- a: input, 1-bit
- b: input, 1-bit
- y: output, 1-bit
Behavior:
- Combinational: y = a & b.
Verification:
- Toggle inputs through all 4 combinations.
- Coverage goals: branch 0.5, toggle 0.5.
Architecture:
- Pure combinational assign.
Acceptance:
- Output matches truth table for all input pairs; coverage goals met.""",
    },
    {
        "name": "mux2",
        "spec": """Module: mux2
2:1 combinational multiplexer.
Signals:
- a: input, 1-bit
- b: input, 1-bit
- sel: input, 1-bit select
- y: output, 1-bit
Behavior:
- Combinational: if sel=0, y=a; if sel=1, y=b.
Verification:
- Test sel=0/1 with varied a/b.
- Coverage goals: branch 0.6, toggle 0.6.
Architecture:
- Combinational assign implementing mux.
Acceptance:
- Output follows selected input for all combinations; coverage goals met.""",
    },
    {
        "name": "counter3",
        "spec": """Module: counter3
3-bit synchronous up-counter with enable and async active-low reset.
Signals:
- clk: input, clock
- rst_n: input, active-low async reset
- en: input, active-high enable
- count[2:0]: output, current count value
Behavior:
- On reset, clear count to 0.
- On each rising edge of clk, if en=1, increment count by 1; if en=0, hold count.
Verification:
- Test reset behavior and enable-driven increments.
- Coverage goals: branch 0.6, toggle 0.6.
Architecture:
- Single always block with enable gate.
Acceptance:
- Increments on enable, clears on reset; tests pass and coverage goals met.""",
    },
    {
        "name": "accum4",
        "spec": """Module: accum4
4-bit accumulator with enable and synchronous active-low reset.
Signals:
- clk: input, clock
- rst_n: input, active-low synchronous reset
- en: input, active-high enable
- in_data[3:0]: input, value to add
- accum[3:0]: output, accumulated sum
Behavior:
- On reset, accum <= 0.
- On each rising edge of clk, if en=1, accum <= accum + in_data (wrap on overflow); if en=0, hold value.
Verification:
- Test reset clears, enable-driven accumulation, hold when disabled, wraparound on overflow.
- Coverage goals: branch 0.7, toggle 0.7.
Architecture:
- Single always block with registered accumulator.
Acceptance:
- Accum reflects running sum per spec; tests pass and coverage goals met.""",
    },
]


def run_case(case: Dict[str, str], timeout: float) -> Dict[str, str]:
    clean_artifacts()
    configure_observability(run_name=f"suite_{case['name']}", default_tags=["suite"])
    spec_flow.collect_specs_from_text(case["name"], case["spec"], interactive=False)

    design_context = ARTIFACTS_GEN / "design_context.json"
    dag_path = ARTIFACTS_GEN / "dag.json"

    params = connection_params_from_env()
    stop_event = threading.Event()
    workers = start_workers(params, stop_event)
    status = "SUCCESS"
    rtl_path = ""
    try:
        planner_stop = threading.Event()
        planner_worker = PlannerWorker(params, planner_stop)
        planner_worker.start()
        try:
            run_planner_task(params, timeout=timeout)
        finally:
            planner_stop.set()
            planner_worker.join(timeout=1.0)
        DemoOrchestrator(params, design_context, dag_path, ARTIFACTS_GEN, REPO_ROOT / "artifacts" / "task_memory").run(timeout_s=timeout)
        ctx = design_context.read_text()
        if ctx:
            import json

            dc = json.loads(ctx)
            node = next(iter(dc.get("nodes", {}).values()), {})
            rtl_rel = node.get("rtl_file")
            if rtl_rel:
                rtl_path = str((ARTIFACTS_GEN / rtl_rel).resolve())
    except Exception as exc:  # noqa: BLE001
        status = f"ERROR: {exc}"
    finally:
        stop_workers(workers, stop_event)
        tracker = get_tracker()
        tracker.finalize()
        totals = tracker.get_totals()
        summary_path = tracker.summary_path
    if not rtl_path:
        status = status if status != "SUCCESS" else "FAILED (no RTL emitted)"
    return {"name": case["name"], "status": status, "rtl": rtl_path, "totals": totals, "summary": str(summary_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run increasing-complexity pipeline smoke tests.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-case timeout in seconds")
    args = parser.parse_args()

    results = []
    for case in SUITE:
        print(f"\n=== Running case: {case['name']} ===")
        results.append(run_case(case, args.timeout))

    print("\n=== Summary ===")
    for r in results:
        cost = r.get("totals", {}).get("estimated_cost_usd", 0)
        print(f"{r['name']}: {r['status']}" + (f" | RTL: {r['rtl']}" if r['rtl'] else "") + f" | est_cost: ${cost:.6f} | summary: {r.get('summary','')}")


if __name__ == "__main__":
    main()
