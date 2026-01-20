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
from workers.distill.worker import DistillWorker
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text())


def _write_fixture(dst: Path, payload: dict) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, indent=2))


def _make_task(entity_type, task_type, context: dict) -> TaskMessage:
    return TaskMessage(entity_type=entity_type, task_type=task_type, context=context)


def _run_stage(worker, task: TaskMessage, task_memory: TaskMemory, node_id: str, stage: str):
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
            ctx = ctx_builder.build(node_id)
            results[node_id] = {}

            result = _run_stage(
                workers["impl"],
                _make_task(EntityType.REASONING, AgentType.IMPLEMENTATION, ctx),
                task_memory,
                node_id,
                "impl",
            )
            results[node_id]["impl"] = result
            if result.status is not TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["lint"],
                _make_task(EntityType.LIGHT_DETERMINISTIC, WorkerType.LINTER, ctx),
                task_memory,
                node_id,
                "lint",
            )
            results[node_id]["lint"] = result
            if result.status is not TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            if ctx.get("verification_scope") != "full":
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["tb"],
                _make_task(EntityType.REASONING, AgentType.TESTBENCH, ctx),
                task_memory,
                node_id,
                "tb",
            )
            results[node_id]["tb"] = result
            if result.status is not TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["sim"],
                _make_task(EntityType.HEAVY_DETERMINISTIC, WorkerType.SIMULATOR, ctx),
                task_memory,
                node_id,
                "sim",
            )
            results[node_id]["sim"] = result
            if result.status is TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["distill"],
                _make_task(EntityType.LIGHT_DETERMINISTIC, WorkerType.DISTILLATION, ctx),
                task_memory,
                node_id,
                "distill",
            )
            results[node_id]["distill"] = result
            if result.status is not TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["reflect"],
                _make_task(EntityType.REASONING, AgentType.REFLECTION, ctx),
                task_memory,
                node_id,
                "reflect",
            )
            results[node_id]["reflect"] = result
            if result.status is not TaskStatus.SUCCESS:
                pending.remove(node_id)
                done.add(node_id)
                continue

            result = _run_stage(
                workers["debug"],
                _make_task(EntityType.REASONING, AgentType.DEBUG, ctx),
                task_memory,
                node_id,
                "debug",
            )
            results[node_id]["debug"] = result
            pending.remove(node_id)
            done.add(node_id)

    return results


def _stub_lint_and_sim(monkeypatch, sim_fail: bool):
    monkeypatch.setattr("workers.lint.worker.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_lint_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    def fake_sim_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            if any(arg.startswith("+DUMP_FILE=") for arg in cmd):
                dump_arg = next(arg for arg in cmd if arg.startswith("+DUMP_FILE="))
                dump_path = Path(dump_arg.split("=", 1)[1])
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text("vcd")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if sim_fail:
                return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: cycle=8 time=80", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_lint_run)
    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_sim_run)


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
                    "suggested_changes": ["change"],
                    "risks": [],
                    "next_steps": ["step"],
                }
            )
        )
    )

    lint = LintWorker(connection_params=None, stop_event=None)
    lint.verilator = "verilator"
    sim = SimulationWorker(connection_params=None, stop_event=None)
    distill = DistillWorker(connection_params=None, stop_event=None)
    return {
        "impl": impl,
        "lint": lint,
        "tb": tb,
        "sim": sim,
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
    _stub_lint_and_sim(monkeypatch, sim_fail=False)

    ctx_builder = DemoContextBuilder(design_context_path, rtl_root)
    task_memory = TaskMemory(task_memory_root)
    results = _run_execution(ctx_builder, dag, workers, task_memory)

    assert results["event_logger_top"]["sim"].status is TaskStatus.SUCCESS
    assert (task_memory_root / "event_logger_top" / "sim" / "log.txt").exists()

    for node_id in ("axi_lite_regs", "event_fifo"):
        assert (task_memory_root / node_id / "impl" / "log.txt").exists()
        assert (task_memory_root / node_id / "lint" / "log.txt").exists()
        assert not (task_memory_root / node_id / "tb" / "log.txt").exists()
        assert not (task_memory_root / node_id / "sim" / "log.txt").exists()


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
    _stub_lint_and_sim(monkeypatch, sim_fail=True)

    ctx_builder = DemoContextBuilder(design_context_path, rtl_root)
    task_memory = TaskMemory(task_memory_root)
    results = _run_execution(ctx_builder, dag, workers, task_memory)

    assert results["event_logger_top"]["sim"].status is TaskStatus.FAILURE
    assert (task_memory_root / "event_logger_top" / "distill" / "distilled_dataset.json").exists()
    assert (task_memory_root / "event_logger_top" / "reflect" / "reflection_insights.json").exists()
    assert (task_memory_root / "event_logger_top" / "debug" / "reflections.json").exists()
