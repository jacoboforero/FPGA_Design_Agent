"""
Local helper to generate spec artifacts with placeholders for missing fields.
Enhanced to run the full system: spec -> orchestrator -> verilog -> verilog_eval testing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pika

# Suppress async cleanup warnings from httpx/anyio
warnings.filterwarnings("ignore", message=".*Event loop is closed.*")
warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="asyncio")
warnings.filterwarnings("ignore", category=ResourceWarning)
# Suppress exceptions during finalization (httpx/anyio cleanup)
import logging
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("anyio").setLevel(logging.CRITICAL)

from agents.common.llm_gateway import init_llm_gateway
from agents.spec_helper.checklist import build_empty_checklist, list_missing_fields, set_field
from agents.spec_helper.llm_helper import generate_field_draft, update_checklist_from_spec
from apps.cli import spec_flow
from apps.cli.cli import connection_params_from_env, start_workers, stop_workers
from orchestrator.orchestrator_service import DemoOrchestrator
from agents.planner.worker import PlannerWorker
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = spec_flow.SPEC_DIR
ARTIFACTS_GEN = REPO_ROOT / "artifacts" / "generated"
TASK_MEMORY_ROOT = REPO_ROOT / "artifacts" / "task_memory"
VERILOG_EVAL_DIR = REPO_ROOT / "verilog_eval" / "dataset_spec-to-rtl"

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


def _placeholder_for(field_path: str, field_type: str, item_keys: List[str] | None, module_name: str) -> Any:
    if field_path == "L2.clocking":
        return [{"clock_name": "clk"}]
    if field_path == "L2.signals":
        return [{"name": "sig0", "direction": "INPUT", "width_expr": "1"}]
    if field_path == "L3.reset_constraints":
        return {"min_cycles_after_reset": 0}
    if field_path == "L4.block_diagram":
        return [{"node_id": module_name, "description": "TBD", "node_type": "module"}]
    if field_path == "L4.assertion_plan":
        return {"sva": ["TBD"], "scoreboard_assertions": ["TBD"]}
    if field_path == "L5.required_artifacts":
        return [{"name": "rtl", "description": "TBD"}]
    if field_path == "L5.acceptance_metrics":
        return [{"metric_id": "acc0", "description": "TBD", "operator": ">=", "target_value": "0"}]

    if field_type == "text":
        return "TBD"
    if field_type == "list":
        return ["TBD"]
    if field_type in ("map", "object"):
        if item_keys:
            return {key: "TBD" for key in item_keys}
        return {"notes": "TBD"}
    if field_type == "list_of_objects":
        if item_keys:
            return [{key: "TBD" for key in item_keys}]
        return [{"notes": "TBD"}]
    return "TBD"


def _run_planner_task(params, timeout: float = 60.0) -> None:
    """Run the planner agent to generate design context and DAG."""
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
                time.sleep(0.05)
                continue
            result = ResultMessage.model_validate_json(body)
            if result.task_id != task.task_id:
                continue
            if result.status is not TaskStatus.SUCCESS:
                raise RuntimeError(f"Planning failed: {result.log_output}")
            print(f"✓ Planner completed successfully")
            return
    raise RuntimeError("Planner timed out waiting for results.")


def _clean_artifacts() -> None:
    """Clean previous generation artifacts."""
    shutil.rmtree(ARTIFACTS_GEN, ignore_errors=True)
    print("Cleaned artifact directory")


def _run_orchestrator(params, timeout: float = 180.0) -> dict[str, Any]:
    """Run the orchestrator to generate Verilog from the spec."""
    design_context_path = ARTIFACTS_GEN / "design_context.json"
    dag_path = ARTIFACTS_GEN / "dag.json"

    stop_event = threading.Event()
    workers = start_workers(params, stop_event)
    
    try:
        # Start planner worker
        planner_stop = threading.Event()
        planner_worker = PlannerWorker(params, planner_stop)
        planner_worker.start()
        try:
            _run_planner_task(params, timeout=timeout)
        finally:
            planner_stop.set()
            planner_worker.join(timeout=1.0)
        
        # Run orchestrator
        print("Running orchestrator to generate Verilog...")
        DemoOrchestrator(params, design_context_path, dag_path, ARTIFACTS_GEN, TASK_MEMORY_ROOT).run(timeout_s=timeout)
        
        # Extract RTL path from design context
        if not design_context_path.exists():
            raise RuntimeError("Design context not generated")
        
        design_context = json.loads(design_context_path.read_text())
        nodes = design_context.get("nodes", {})
        if not nodes:
            raise RuntimeError("No nodes in design context")
        
        # Get first node's RTL file
        node = next(iter(nodes.values()))
        rtl_rel = node.get("rtl_file")
        if not rtl_rel:
            raise RuntimeError("No RTL file in design context")
        
        rtl_path = ARTIFACTS_GEN / rtl_rel
        if not rtl_path.exists():
            raise RuntimeError(f"RTL file not found: {rtl_path}")
        
        module_name = node.get("module_name", "unknown")
        print(f"✓ Orchestrator generated RTL: {rtl_path}")
        
        return {
            "rtl_path": rtl_path,
            "module_name": module_name,
            "design_context": design_context,
        }
    finally:
        stop_workers(workers, stop_event)


def _find_verilog_eval_files(prob_name: str) -> dict[str, Path]:
    """Find the test and reference files for a verilog_eval problem."""
    # Match pattern like Prob001_zero
    pattern_parts = prob_name.split("_")
    if len(pattern_parts) < 2:
        return {}
    
    prob_num = pattern_parts[0]  # e.g., Prob001
    
    # Find matching files
    matches = list(VERILOG_EVAL_DIR.glob(f"{prob_num}_*_test.sv"))
    if not matches:
        return {}
    
    test_file = matches[0]
    base = test_file.stem.rsplit("_test", 1)[0]
    ref_file = VERILOG_EVAL_DIR / f"{base}_ref.sv"
    
    if not ref_file.exists():
        return {}
    
    return {
        "test": test_file,
        "ref": ref_file,
        "base": base,
    }


def _run_verilog_eval_test(generated_rtl: Path, prob_name: str) -> dict[str, Any]:
    """
    Test the generated Verilog using verilog_eval's iverilog test harness.
    Returns dict with 'passed', 'compile_log', 'test_log' keys.
    """
    files = _find_verilog_eval_files(prob_name)
    if not files:
        return {
            "passed": False,
            "error": f"No verilog_eval test files found for {prob_name}",
        }
    
    test_file = files["test"]
    ref_file = files["ref"]
    
    # Create a temporary test directory
    test_dir = REPO_ROOT / "artifacts" / "verilog_eval_tests" / prob_name
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy generated RTL to test directory
    generated_copy = test_dir / generated_rtl.name
    shutil.copy(generated_rtl, generated_copy)
    
    # Compile with iverilog
    compile_log = test_dir / "compile.log"
    test_bin = test_dir / "test_bin"
    
    compile_cmd = [
        "iverilog",
        "-Wall",
        "-Winfloop",
        "-Wno-timescale",
        "-g2012",
        "-s", "tb",
        "-o", str(test_bin),
        str(generated_copy),
        str(test_file),
        str(ref_file),
    ]
    
    try:
        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=test_dir,
        )
        compile_log.write_text(f"Command: {' '.join(compile_cmd)}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n")
        
        if result.returncode != 0:
            return {
                "passed": False,
                "stage": "compile",
                "compile_log": str(compile_log),
                "error": "Compilation failed",
            }
        
        # Run the test
        test_log = test_dir / "test.log"
        test_result = subprocess.run(
            [str(test_bin)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=test_dir,
        )
        test_log.write_text(f"STDOUT:\n{test_result.stdout}\n\nSTDERR:\n{test_result.stderr}\n")
        
        # Check for success markers
        passed = test_result.returncode == 0 and "Mismatches: 0" in test_result.stdout
        
        return {
            "passed": passed,
            "stage": "test" if passed else "runtime",
            "compile_log": str(compile_log),
            "test_log": str(test_log),
            "returncode": test_result.returncode,
        }
    
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "stage": "timeout",
            "error": "Test execution timed out",
        }
    except Exception as exc:
        return {
            "passed": False,
            "stage": "error",
            "error": str(exc),
        }


def _derive_module_names(spec_text: str) -> tuple[str, str]:
    """
    Extract module name from spec text using multiple regex patterns.
    Falls back to 'demo_module' if no match found.
    """
    # Try multiple regex patterns to match different prompt formats
    patterns = [
        r'module\s+named\s+["\`\'\']?(\w+)["\`\'\']?',      # "module named TopModule"
        r'[Mm]odule\s*names?\s*:?\s*["\`\'\']?(\w+)["\`\'\']?',  # "Module: TopModule" or "Module name: X"
        r'implement\s+(?:a\s+)?(?:module\s+)?["\`\'\']?(\w+)["\`\'\']?',  # "implement module TopModule"
        r'named\s+["\`\'\']?(\w+)["\`\'\']?\s+(?:with|that|which)',  # "named TopModule with"
        r'[Cc]reate\s+(?:a\s+)?(?:module\s+)?["\`\'\']?(\w+)["\`\'\']?',  # "Create module X"
        r'top[_\s]module\s*:?\s*["\`\'\']?(\w+)["\`\'\']?',  # "top module: X"
    ]
    
    module_name = None
    for pattern in patterns:
        match = re.search(pattern, spec_text, re.IGNORECASE)
        if match:
            module_name = match.group(1)
            break
    
    # If still no match, try the original method
    if not module_name:
        module_name = spec_flow._extract_module_name(spec_text)
    
    # Final fallback
    if not module_name:
        module_name = "demo_module"
    
    module_name = spec_flow._sanitize_name(module_name)
    top_module = spec_flow._extract_top_module(spec_text) or module_name
    top_module = spec_flow._sanitize_name(top_module)
    return module_name, top_module


def _generate_checklist(spec_text: str, module_name: str) -> Dict[str, Any]:
    gateway = init_llm_gateway()
    if not gateway:
        raise RuntimeError(
            "LLM gateway unavailable. Set USE_LLM=1 and provider API key(s) in this shell before running."
        )
    checklist = build_empty_checklist()
    print("Generating initial checklist from spec text...")
    checklist = update_checklist_from_spec(gateway, spec_text, checklist)
    set_field(checklist, "module_name", module_name)

    missing = list_missing_fields(checklist)
    while missing:
        field = missing[0]
        print(f"Drafting missing field: {field.path}")
        value = None
        last_draft = None
        for attempt in range(1, 4):
            draft = generate_field_draft(gateway, field, checklist, spec_text)
            last_draft = draft
            value = spec_flow._coerce_answer_value(field, draft.get("value"))
            if value is not None and not spec_flow._value_missing(field, value):
                break
            print(f"  Attempt {attempt} returned an empty/invalid value.")
            value = None
        if value is None or spec_flow._value_missing(field, value):
            draft_text = "" if not isinstance(last_draft, dict) else str(last_draft.get("draft_text") or "").strip()
            preview = draft_text[:200] + ("..." if len(draft_text) > 200 else "")
            raise RuntimeError(
                f"Spec helper draft missing required field after retries: {field.path}. "
                f"Last draft_text preview: {preview or '<<empty>>'}"
            )
        set_field(checklist, field.path, value)
        missing = list_missing_fields(checklist)

    return checklist


def _run_single_spec(spec_path: Path, run_full_pipeline: bool = False, timeout: float = 180.0, skip_on_spec_error: bool = False) -> dict[str, Any]:
    """Generate spec and optionally run full pipeline through verilog_eval."""
    spec_text = spec_path.read_text().strip()
    module_name, top_module = _derive_module_names(spec_text)

    result = {
        "spec_path": str(spec_path),
        "module_name": module_name,
    }

    # Try to generate checklist
    try:
        checklist = _generate_checklist(spec_text, module_name)
    except RuntimeError as e:
        if "Spec helper draft missing required field" in str(e):
            error_msg = f"Spec generation failed (prompt too simple): {str(e)[:100]}"
            print(f"⚠️  {error_msg}")
            if skip_on_spec_error:
                result["skipped"] = True
                result["error"] = error_msg
                return result
            raise
        raise

    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_spec_path = SPEC_DIR / f"spec_input_local_{spec_path.stem}_{stamp}.txt"

    spec_id = spec_flow._write_artifacts(
        spec_text,
        checklist,
        output_spec_path,
        module_name=module_name,
    )
    
    # Extract module names from L4 block diagram, filtering out non-module entities
    l4_data = checklist.get("L4", {})
    block_diagram = l4_data.get("block_diagram", [])
    module_names = []
    
    for node in block_diagram:
        if isinstance(node, dict) and node.get("node_type") == "module":
            node_id = node.get("node_id")
            if node_id and node_id != module_name and node_id != top_module:
                # Exclude single-letter names (FSM states) and logic blocks
                if len(node_id) > 2 and not node_id.endswith('_logic'):
                    module_names.append(node_id)
    
    # For single-module designs, just use the top module
    if not module_names:
        module_names = [module_name]
    
    spec_flow._write_lock(module_names, top_module, spec_id)

    print(f"✓ Wrote spec artifacts for module '{module_name}' from {spec_path.name}")
    
    result["spec_artifacts"] = str(output_spec_path)
    
    if not run_full_pipeline:
        return result
    
    # Run full pipeline
    try:
        # Check RabbitMQ connection
        rabbit_url = os.getenv("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
        try:
            params = connection_params_from_env()
            conn = pika.BlockingConnection(params)
            conn.close()
        except Exception as exc:
            raise RuntimeError(f"RabbitMQ not reachable at {rabbit_url}. Start docker-compose in infrastructure/. Error: {exc}")
        
        # Clean artifacts
        _clean_artifacts()
        
        # Run orchestrator to generate Verilog
        orch_result = _run_orchestrator(params, timeout=timeout)
        result.update(orch_result)
        
        # Run verilog_eval test
        print(f"Running verilog_eval test for {spec_path.stem}...")
        test_result = _run_verilog_eval_test(orch_result["rtl_path"], spec_path.stem)
        result["test"] = test_result
        
        if test_result.get("passed"):
            print(f"✓ PASS: {spec_path.stem}")
        else:
            print(f"✗ FAIL: {spec_path.stem} - {test_result.get('error', test_result.get('stage'))}")
        
    except Exception as exc:
        result["error"] = str(exc)
        print(f"✗ ERROR: {spec_path.stem} - {exc}")
    
    return result


def _run_batch(spec_paths: List[Path], run_full_pipeline: bool = False, timeout: float = 180.0, skip_on_spec_error: bool = True) -> int:
    failures: List[str] = []
    results: List[dict[str, Any]] = []
    
    for spec_path in spec_paths:
        print(f"\n{'='*80}")
        print(f"Processing {spec_path.name}")
        print('='*80)
        try:
            result = _run_single_spec(spec_path, run_full_pipeline=run_full_pipeline, timeout=timeout, skip_on_spec_error=skip_on_spec_error)
            results.append(result)
            
            # Check if skipped
            if result.get("skipped"):
                continue
            
            if run_full_pipeline:
                test_result = result.get("test", {})
                if not test_result.get("passed"):
                    error_msg = test_result.get("error", test_result.get("stage", "unknown"))
                    failures.append(f"{spec_path.name}: {error_msg}")
        except Exception as exc:  # noqa: BLE001
            print(f"Failed: {spec_path.name} -> {exc}")
            failures.append(f"{spec_path.name}: {exc}")
            results.append({"spec_path": str(spec_path), "error": str(exc)})

    # Print summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print('='*80)
    
    skipped = sum(1 for r in results if r.get("skipped"))
    if skipped:
        print(f"\nSkipped: {skipped} (spec generation failed - prompts too simple)")
    
    if run_full_pipeline:
        passed = sum(1 for r in results if r.get("test", {}).get("passed"))
        total = len([r for r in results if not r.get("skipped")])
        if total > 0:
            print(f"\nPass rate: {passed}/{total} ({100*passed/total:.1f}%)")
        
        for r in results:
            spec_name = Path(r["spec_path"]).stem
            if r.get("skipped"):
                print(f"  SKIP: {spec_name}")
            elif "test" in r:
                status = "PASS" if r["test"].get("passed") else "FAIL"
                print(f"  {status}: {spec_name}")
            elif "error" in r:
                print(f"  ERROR: {spec_name} - {r['error'][:80]}")
    
    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"  - {item}")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate spec artifacts and optionally run full pipeline with verilog_eval testing."
    )
    parser.add_argument("--spec-file", help="Path to the spec text file.")
    parser.add_argument(
        "--batch",
        nargs="?",
        const=10,
        type=int,
        help="Run Prob001-ProbNN from processed_prompts (default NN=10).",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Don't skip problems that fail spec generation; fail instead.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full pipeline: spec -> orchestrator -> verilog -> verilog_eval test.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Timeout in seconds for orchestrator execution (default: 180).",
    )
    args = parser.parse_args()

    if args.batch is not None:
        repo_root = Path(__file__).resolve().parents[1]
        prompt_dir = repo_root / "processed_prompts"
        count = args.batch
        if count < 1:
            raise SystemExit("--batch must be >= 1")
        spec_paths = [prompt_dir / f"Prob{idx:03d}_" for idx in range(1, count + 1)]
        resolved: List[Path] = []
        for stub in spec_paths:
            matches = list(prompt_dir.glob(stub.name + "*.txt"))
            if not matches:
                resolved.append(stub.with_name(stub.name + "missing.txt"))
                continue
            resolved.append(matches[0])
        missing = [p for p in resolved if not p.exists()]
        if missing:
            names = ", ".join(p.name for p in missing)
            raise FileNotFoundError(f"Missing processed prompt(s): {names}")
        
        print(f"\n{'='*80}")
        print(f"Running batch of {count} problems")
        if args.full:
            print("Mode: Full pipeline (spec -> orchestrator -> verilog -> verilog_eval)")
            print(f"Timeout: {args.timeout}s per problem")
            print(f"Skip on spec error: {not args.no_skip}")
        else:
            print("Mode: Spec generation only")
        print('='*80)
        
        raise SystemExit(_run_batch(resolved, run_full_pipeline=args.full, timeout=args.timeout, skip_on_spec_error=not args.no_skip))

    if not args.spec_file:
        raise SystemExit("--spec-file is required unless --batch is used.")

    spec_path = Path(args.spec_file).expanduser().resolve()
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")

    result = _run_single_spec(spec_path, run_full_pipeline=args.full, timeout=args.timeout, skip_on_spec_error=False)
    
    if args.full:
        if result.get("skipped"):
            print(f"Skipped due to spec generation failure")
            raise SystemExit(1)
        test_result = result.get("test", {})
        exit_code = 0 if test_result.get("passed") else 1
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
