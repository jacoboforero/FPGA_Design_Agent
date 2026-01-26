from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agents.debug.worker import DebugWorker
from agents.implementation.worker import ImplementationWorker
from agents.reflection.worker import ReflectionWorker
from agents.testbench.worker import TestbenchWorker
from core.schemas.contracts import AgentType, EntityType, TaskMessage, TaskStatus, WorkerType
from orchestrator.context_builder import DemoContextBuilder
from orchestrator.task_memory import TaskMemory
from tests.execution.helpers import FakeGateway, FakeResponse
from workers.acceptance.worker import AcceptanceWorker
from workers.distill.worker import DistillWorker
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker
from workers.tb_lint.worker import TestbenchLintWorker


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_fixture(dst: Path, payload: dict) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, indent=2))


def _make_task(entity_type, task_type, context: dict) -> TaskMessage:
    return TaskMessage(entity_type=entity_type, task_type=task_type, context=context)


def _stage_key(kind: str, attempt: int | None = None) -> str:
    if attempt is None:
        return kind
    return f"{kind}_attempt{attempt}"


def _run_stage(worker, task: TaskMessage, task_memory: TaskMemory, node_id: str, stage: str):
    print(f"[exec] {node_id}:{stage} start")
    result = worker.handle_task(task)
    task_memory.record_log(node_id, stage, result.log_output)
    if result.artifacts_path:
        task_memory.record_artifact_path(node_id, stage, result.artifacts_path)
    if result.reflection_insights:
        task_memory.record_json(
            node_id,
            stage,
            "reflection_insights.json",
            result.reflection_insights.model_dump(mode="json"),
        )
    if result.reflections:
        task_memory.record_json(node_id, stage, "reflections.json", json.loads(result.reflections))
    print(f"[exec] {node_id}:{stage} status={result.status.value}")
    if result.log_output:
        summary = result.log_output.splitlines()[0].strip()
        if summary:
            print(f"[exec] {node_id}:{stage} log_head={summary}")
    return result


def _run_execution(
    ctx_builder: DemoContextBuilder,
    dag: dict,
    workers: dict,
    task_memory: TaskMemory,
) -> dict:
    deps_map = {n["id"]: set(n.get("deps", [])) for n in dag["nodes"]}
    pending = set(deps_map.keys())
    done = set()
    results = {}

    while pending:
        ready = [node for node in pending if deps_map[node] <= done]
        if not ready:
            raise RuntimeError("No ready nodes; DAG has a cycle.")
        for node_id in ready:
            print(f"[exec] node={node_id} ready")
            ctx = ctx_builder.build(node_id)
            results[node_id] = {}
            attempt = 1
            debug_attempts_by_reason = {"tb_lint": 0, "sim": 0}

            result = _run_stage(
                workers["impl"],
                _make_task(EntityType.REASONING, AgentType.IMPLEMENTATION, ctx),
                task_memory,
                node_id,
                _stage_key("impl"),
            )
            results[node_id][_stage_key("impl")] = result
            if result.status is not TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            ctx["attempt"] = attempt
            result = _run_stage(
                workers["lint"],
                _make_task(EntityType.LIGHT_DETERMINISTIC, WorkerType.LINTER, ctx),
                task_memory,
                node_id,
                _stage_key("lint", attempt),
            )
            results[node_id][_stage_key("lint", attempt)] = result
            if result.status is not TaskStatus.SUCCESS:
                print(f"[exec] node={node_id} failed after lint")
                pending.remove(node_id)
                done.add(node_id)
                continue

            if ctx.get("verification_scope") != "full":
                print(f"[exec] node={node_id} verification_scope=lite; skipping tb/sim")
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["tb"],
                _make_task(EntityType.REASONING, AgentType.TESTBENCH, ctx),
                task_memory,
                node_id,
                _stage_key("tb"),
            )
            results[node_id][_stage_key("tb")] = result
            if result.status is not TaskStatus.SUCCESS:
                print(f"[exec] node={node_id} failed after tb")
                pending.remove(node_id)
                done.add(node_id)
                continue

            # TB lint may fail and require debug-based retries before any sim is run.
            while True:
                ctx["attempt"] = attempt
                result = _run_stage(
                    workers["tb_lint"],
                    _make_task(EntityType.LIGHT_DETERMINISTIC, WorkerType.TESTBENCH_LINTER, ctx),
                    task_memory,
                    node_id,
                    _stage_key("tb_lint", attempt),
                )
                results[node_id][_stage_key("tb_lint", attempt)] = result
                if result.status is TaskStatus.SUCCESS:
                    break
                if debug_attempts_by_reason["tb_lint"] >= 2:
                    print(f"[exec] node={node_id} tb_lint failed; retries exhausted")
                    pending.remove(node_id)
                    done.add(node_id)
                    break
                print(f"[exec] node={node_id} tb_lint failed; entering debug (attempt={attempt})")
                debug_attempts_by_reason["tb_lint"] += 1
                ctx["debug_reason"] = "tb_lint"
                result = _run_stage(
                    workers["debug"],
                    _make_task(EntityType.REASONING, AgentType.DEBUG, ctx),
                    task_memory,
                    node_id,
                    _stage_key("debug", attempt),
                )
                results[node_id][_stage_key("debug", attempt)] = result
                if result.status is not TaskStatus.SUCCESS:
                    pending.remove(node_id)
                    done.add(node_id)
                    break
                attempt += 1
                ctx.pop("debug_reason", None)
            if node_id not in pending:
                continue

            # Simulation loop: on sim failure, distill/reflect/debug patch then re-run.
            while True:
                ctx["attempt"] = attempt
                result = _run_stage(
                    workers["sim"],
                    _make_task(EntityType.HEAVY_DETERMINISTIC, WorkerType.SIMULATOR, ctx),
                    task_memory,
                    node_id,
                    _stage_key("sim", attempt),
                )
                results[node_id][_stage_key("sim", attempt)] = result
                if result.status is TaskStatus.SUCCESS:
                    result = _run_stage(
                        workers["acceptance"],
                        _make_task(EntityType.LIGHT_DETERMINISTIC, WorkerType.ACCEPTANCE, ctx),
                        task_memory,
                        node_id,
                        _stage_key("acceptance", attempt),
                    )
                    results[node_id][_stage_key("acceptance", attempt)] = result
                    pending.remove(node_id)
                    done.add(node_id)
                    break

                print(f"[exec] node={node_id} sim failed; entering distill/reflect (attempt={attempt})")

                result = _run_stage(
                    workers["distill"],
                    _make_task(EntityType.LIGHT_DETERMINISTIC, WorkerType.DISTILLATION, ctx),
                    task_memory,
                    node_id,
                    _stage_key("distill", attempt),
                )
                results[node_id][_stage_key("distill", attempt)] = result
                if result.status is not TaskStatus.SUCCESS:
                    pending.remove(node_id)
                    done.add(node_id)
                    break

                result = _run_stage(
                    workers["reflect"],
                    _make_task(EntityType.REASONING, AgentType.REFLECTION, ctx),
                    task_memory,
                    node_id,
                    _stage_key("reflect", attempt),
                )
                results[node_id][_stage_key("reflect", attempt)] = result
                if result.status is not TaskStatus.SUCCESS:
                    pending.remove(node_id)
                    done.add(node_id)
                    break

                if debug_attempts_by_reason["sim"] >= 2:
                    print(f"[exec] node={node_id} debug retries exhausted; failing")
                    pending.remove(node_id)
                    done.add(node_id)
                    break
                debug_attempts_by_reason["sim"] += 1
                ctx["debug_reason"] = "sim"
                result = _run_stage(
                    workers["debug"],
                    _make_task(EntityType.REASONING, AgentType.DEBUG, ctx),
                    task_memory,
                    node_id,
                    _stage_key("debug", attempt),
                )
                results[node_id][_stage_key("debug", attempt)] = result
                if result.status is not TaskStatus.SUCCESS:
                    pending.remove(node_id)
                    done.add(node_id)
                    break
                attempt += 1
                ctx.pop("debug_reason", None)

    return results


def _stub_lint_and_sim(monkeypatch, sim_fail_sequence: list[bool] | None = None, tb_lint_fail_sequence: list[bool] | None = None):
    monkeypatch.setattr("workers.lint.worker.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("workers.tb_lint.worker.shutil.which", lambda name: f"/bin/{name}")

    sim_fail_sequence = sim_fail_sequence or [False]
    tb_lint_fail_sequence = tb_lint_fail_sequence or [False]
    sim_calls = {"n": 0}
    tb_lint_calls = {"n": 0}

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("verilator"):
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
        if cmd[0].endswith("iverilog"):
            if "-tnull" in cmd:
                idx = min(tb_lint_calls["n"], len(tb_lint_fail_sequence) - 1)
                tb_lint_calls["n"] += 1
                if tb_lint_fail_sequence[idx]:
                    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="tb lint error")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            if any(arg.startswith("+DUMP_FILE=") for arg in cmd):
                dump_arg = next(arg for arg in cmd if arg.startswith("+DUMP_FILE="))
                dump_path = Path(dump_arg.split("=", 1)[1])
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text("vcd")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            idx = min(sim_calls["n"], len(sim_fail_sequence) - 1)
            sim_calls["n"] += 1
            if sim_fail_sequence[idx]:
                return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: cycle=8 time=80", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    monkeypatch.setattr("workers.tb_lint.worker.subprocess.run", fake_run)


def _build_workers():
    impl = ImplementationWorker(connection_params=None, stop_event=None)
    impl.gateway = FakeGateway(FakeResponse(content="module demo; endmodule\n"))

    tb = TestbenchWorker(connection_params=None, stop_event=None)
    tb.gateway = FakeGateway(FakeResponse(content="module tb_demo; initial $finish; endmodule\n"))

    refl = ReflectionWorker(connection_params=None, stop_event=None)
    refl.gateway = FakeGateway(
        FakeResponse(
            content=json.dumps(
                {
                    "hypotheses": ["h1"],
                    "likely_failure_points": ["p1"],
                    "recommended_probes": ["probe"],
                    "confidence_score": 0.5,
                    "analysis_notes": "ok",
                }
            )
        )
    )

    dbg = DebugWorker(connection_params=None, stop_event=None)
    dbg.gateway = FakeGateway(
        FakeResponse(
            content=json.dumps(
                {
                    "summary": "ok",
                    "touched_files": ["tb"],
                    "rtl_lines": None,
                    "tb_lines": ["module tb_demo;", "  initial $finish;", "endmodule"],
                    "risks": [],
                    "next_steps": ["step"],
                }
            )
        )
    )

    lint = LintWorker(connection_params=None, stop_event=None)
    lint.verilator = "verilator"
    tb_lint = TestbenchLintWorker(connection_params=None, stop_event=None)
    tb_lint.iverilog = "iverilog"
    sim = SimulationWorker(connection_params=None, stop_event=None)
    acceptance = AcceptanceWorker(connection_params=None, stop_event=None)
    distill = DistillWorker(connection_params=None, stop_event=None)
    return {
        "impl": impl,
        "lint": lint,
        "tb": tb,
        "tb_lint": tb_lint,
        "sim": sim,
        "acceptance": acceptance,
        "distill": distill,
        "reflect": refl,
        "debug": dbg,
    }


def test_execution_pipeline_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "execution"
    design_context = _load_fixture(fixtures_dir / "complex_design_context.json")
    dag = _load_fixture(fixtures_dir / "complex_dag.json")

    design_context_path = tmp_path / "artifacts/generated/design_context.json"
    dag_path = tmp_path / "artifacts/generated/dag.json"
    _write_fixture(design_context_path, design_context)
    _write_fixture(dag_path, dag)

    task_memory_root = tmp_path / "artifacts/task_memory"
    rtl_root = tmp_path / "artifacts/generated"

    workers = _build_workers()
    _stub_lint_and_sim(monkeypatch, sim_fail_sequence=[False], tb_lint_fail_sequence=[False])

    ctx_builder = DemoContextBuilder(design_context_path, rtl_root)
    task_memory = TaskMemory(task_memory_root)
    results = _run_execution(ctx_builder, dag, workers, task_memory)

    assert results["event_logger_top"]["sim_attempt1"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["acceptance_attempt1"].status is TaskStatus.SUCCESS
    assert (task_memory_root / "event_logger_top" / "sim_attempt1" / "log.txt").exists()
    assert (task_memory_root / "event_logger_top" / "acceptance_attempt1" / "log.txt").exists()

    for node_id in ("axi_lite_regs", "event_fifo"):
        assert (task_memory_root / node_id / "impl" / "log.txt").exists()
        assert (task_memory_root / node_id / "lint_attempt1" / "log.txt").exists()
        assert not (task_memory_root / node_id / "tb" / "log.txt").exists()
        assert not (task_memory_root / node_id / "tb_lint_attempt1" / "log.txt").exists()
        assert not (task_memory_root / node_id / "sim_attempt1" / "log.txt").exists()


def test_execution_pipeline_failure_triggers_distill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "execution"
    design_context = _load_fixture(fixtures_dir / "complex_design_context.json")
    dag = _load_fixture(fixtures_dir / "complex_dag.json")

    design_context_path = tmp_path / "artifacts/generated/design_context.json"
    dag_path = tmp_path / "artifacts/generated/dag.json"
    _write_fixture(design_context_path, design_context)
    _write_fixture(dag_path, dag)

    task_memory_root = tmp_path / "artifacts/task_memory"
    rtl_root = tmp_path / "artifacts/generated"

    workers = _build_workers()
    _stub_lint_and_sim(monkeypatch, sim_fail_sequence=[True, True, True], tb_lint_fail_sequence=[False])

    ctx_builder = DemoContextBuilder(design_context_path, rtl_root)
    task_memory = TaskMemory(task_memory_root)
    results = _run_execution(ctx_builder, dag, workers, task_memory)

    assert results["event_logger_top"]["sim_attempt1"].status is TaskStatus.FAILURE
    assert results["event_logger_top"]["sim_attempt2"].status is TaskStatus.FAILURE
    assert results["event_logger_top"]["sim_attempt3"].status is TaskStatus.FAILURE
    assert "acceptance_attempt1" not in results["event_logger_top"]
    assert "acceptance_attempt2" not in results["event_logger_top"]
    assert "acceptance_attempt3" not in results["event_logger_top"]
    assert (task_memory_root / "event_logger_top" / "tb_lint_attempt1" / "log.txt").exists()
    assert (task_memory_root / "event_logger_top" / "distill_attempt1" / "distilled_dataset.json").exists()
    assert (task_memory_root / "event_logger_top" / "reflect_attempt1" / "reflection_insights.json").exists()
    assert (task_memory_root / "event_logger_top" / "debug_attempt1" / "reflections.json").exists()
    assert (task_memory_root / "event_logger_top" / "distill_attempt2" / "distilled_dataset.json").exists()
    assert (task_memory_root / "event_logger_top" / "reflect_attempt2" / "reflection_insights.json").exists()
    assert (task_memory_root / "event_logger_top" / "debug_attempt2" / "reflections.json").exists()
    assert (task_memory_root / "event_logger_top" / "distill_attempt3" / "distilled_dataset.json").exists()
    assert (task_memory_root / "event_logger_top" / "reflect_attempt3" / "reflection_insights.json").exists()
    assert not (task_memory_root / "event_logger_top" / "debug_attempt3" / "reflections.json").exists()


def test_execution_pipeline_tb_lint_failure_triggers_debug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "execution"
    design_context = _load_fixture(fixtures_dir / "complex_design_context.json")
    dag = _load_fixture(fixtures_dir / "complex_dag.json")

    design_context_path = tmp_path / "artifacts/generated/design_context.json"
    dag_path = tmp_path / "artifacts/generated/dag.json"
    _write_fixture(design_context_path, design_context)
    _write_fixture(dag_path, dag)

    task_memory_root = tmp_path / "artifacts/task_memory"
    rtl_root = tmp_path / "artifacts/generated"

    workers = _build_workers()
    _stub_lint_and_sim(monkeypatch, sim_fail_sequence=[False], tb_lint_fail_sequence=[True, False])

    ctx_builder = DemoContextBuilder(design_context_path, rtl_root)
    task_memory = TaskMemory(task_memory_root)
    results = _run_execution(ctx_builder, dag, workers, task_memory)

    assert results["event_logger_top"]["tb_lint_attempt1"].status is TaskStatus.FAILURE
    assert results["event_logger_top"]["debug_attempt1"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["tb_lint_attempt2"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["sim_attempt2"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["acceptance_attempt2"].status is TaskStatus.SUCCESS
    assert (task_memory_root / "event_logger_top" / "tb_lint_attempt1" / "log.txt").exists()
    assert (task_memory_root / "event_logger_top" / "debug_attempt1" / "log.txt").exists()


def test_execution_pipeline_tb_lint_and_sim_failures_have_separate_debug_budgets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "execution"
    design_context = _load_fixture(fixtures_dir / "complex_design_context.json")
    dag = _load_fixture(fixtures_dir / "complex_dag.json")

    design_context_path = tmp_path / "artifacts/generated/design_context.json"
    dag_path = tmp_path / "artifacts/generated/dag.json"
    _write_fixture(design_context_path, design_context)
    _write_fixture(dag_path, dag)

    task_memory_root = tmp_path / "artifacts/task_memory"
    rtl_root = tmp_path / "artifacts/generated"

    workers = _build_workers()
    # TB lint fails once (needs one debug), then passes. Simulation then fails twice and must still
    # get two debug attempts for the sim failure reason.
    _stub_lint_and_sim(monkeypatch, sim_fail_sequence=[True, True, False], tb_lint_fail_sequence=[True, False])

    ctx_builder = DemoContextBuilder(design_context_path, rtl_root)
    task_memory = TaskMemory(task_memory_root)
    results = _run_execution(ctx_builder, dag, workers, task_memory)

    assert results["event_logger_top"]["tb_lint_attempt1"].status is TaskStatus.FAILURE
    assert results["event_logger_top"]["debug_attempt1"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["tb_lint_attempt2"].status is TaskStatus.SUCCESS

    assert results["event_logger_top"]["sim_attempt2"].status is TaskStatus.FAILURE
    assert results["event_logger_top"]["debug_attempt2"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["sim_attempt3"].status is TaskStatus.FAILURE
    assert results["event_logger_top"]["debug_attempt3"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["sim_attempt4"].status is TaskStatus.SUCCESS
    assert results["event_logger_top"]["acceptance_attempt4"].status is TaskStatus.SUCCESS
