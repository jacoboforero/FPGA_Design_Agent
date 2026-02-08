from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.runtime.retry import TaskInputError
from core.schemas.contracts import EntityType, TaskMessage, TaskStatus, WorkerType
from workers.sim.worker import SimulationWorker


def test_sim_worker_missing_rtl_path():
    worker = SimulationWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"node_id": "demo"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_sim_worker_missing_file():
    worker = SimulationWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": "missing.sv", "node_id": "demo"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_sim_worker_missing_tools(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: None)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "Simulation tools missing" in result.log_output


def test_sim_worker_build_failure(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="compile error")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "compile error" in result.log_output


def test_sim_worker_runtime_failure_nonzero_exit(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 1, stdout="Runtime error", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE


def test_sim_worker_fail_marker_exit_zero(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="FAIL: cycle=3 time=30", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "Simulation reported failure" in result.log_output


def test_sim_worker_failure_rerun_waveform(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            if any(arg.startswith("+DUMP_FILE=") for arg in cmd):
                dump_arg = next(arg for arg in cmd if arg.startswith("+DUMP_FILE="))
                dump_path = Path(dump_arg.split("=", 1)[1])
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text("vcd")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: cycle=12 time=120", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert result.artifacts_path
    assert "Waveform written" in result.log_output


def test_sim_worker_failure_no_cycle_info(tmp_path, monkeypatch):
    """Test failure without cycle information - should skip waveform rerun."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            # No cycle info in output
            return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: Something went wrong", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "failure cycle not found" in result.log_output
    assert result.artifacts_path is None


def test_sim_worker_failure_no_node_id(tmp_path, monkeypatch):
    """Test failure without node_id - should skip waveform rerun."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: cycle=5 time=50", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path)},  # No node_id
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "missing node_id" in result.log_output
    assert result.artifacts_path is None


def test_sim_worker_success(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "PASS" in result.log_output


def test_sim_worker_success_with_pass_marker(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="PASS: All checks passed at cycle=10", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "PASS" in result.log_output


def test_sim_worker_success_no_output(tmp_path, monkeypatch):
    """Test success with no output - should show 'Simulation passed' message."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "Simulation passed" in result.log_output


def test_sim_worker_with_testbench(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")
    rtl_path = tmp_path / "demo.sv"
    tb_path = tmp_path / "demo_tb.sv"
    rtl_path.write_text("module demo; endmodule\n")
    tb_path.write_text("module demo_tb; initial $finish; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "tb_path": str(tb_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_sim_worker_timeout_build(tmp_path, monkeypatch):
    """Test timeout during build phase."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "timeout" in result.log_output.lower()


def test_sim_worker_timeout_run(tmp_path, monkeypatch):
    """Test timeout during simulation run."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "timeout" in result.log_output.lower()


def test_sim_worker_combined_stderr_stdout(tmp_path, monkeypatch):
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="stdout msg", stderr="stderr msg")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "stdout msg" in result.log_output or "stderr msg" in result.log_output


def test_sim_worker_multiple_rtl_paths(tmp_path, monkeypatch):
    """Test simulation with multiple RTL files."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")
    rtl_path1 = tmp_path / "demo1.sv"
    rtl_path2 = tmp_path / "demo2.sv"
    rtl_path1.write_text("module demo1; endmodule\n")
    rtl_path2.write_text("module demo2; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={
            "rtl_path": str(rtl_path1),
            "rtl_paths": [str(rtl_path1), str(rtl_path2)],
            "node_id": "demo",
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_sim_worker_missing_rtl_in_paths(tmp_path):
    """Test that missing files in rtl_paths raises TaskInputError."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    rtl_path1 = tmp_path / "demo1.sv"
    rtl_path1.write_text("module demo1; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={
            "rtl_path": str(rtl_path1),
            "rtl_paths": [str(rtl_path1), "missing.sv"],
            "node_id": "demo",
        },
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_sim_worker_empty_rtl_paths_uses_fallback(tmp_path, monkeypatch):
    """Test that empty rtl_paths falls back to using rtl_path."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={
            "rtl_path": str(rtl_path),
            "rtl_paths": [],
            "node_id": "demo",
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_sim_worker_waveform_rerun_from_cycle_zero(tmp_path, monkeypatch):
    """Test waveform rerun when failure is at cycle 0 - should omit window."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            if any(arg.startswith("+DUMP_FILE=") for arg in cmd):
                dump_arg = next(arg for arg in cmd if arg.startswith("+DUMP_FILE="))
                dump_path = Path(dump_arg.split("=", 1)[1])
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text("vcd")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: cycle=0 time=0", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "window omitted" in result.log_output


def test_sim_worker_error_marker_detection(tmp_path, monkeypatch):
    """Test that ERROR marker (not just FAIL) triggers failure."""
    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="ERROR: Assertion failed at cycle=5", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context={"rtl_path": str(rtl_path), "node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "ERROR" in result.log_output
