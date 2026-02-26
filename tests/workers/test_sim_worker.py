from pathlib import Path
import subprocess

import pytest

from workers.sim.worker import SimulationWorker
from core.schemas.contracts import TaskMessage, EntityType, WorkerType, TaskPriority, TaskStatus


def make_task(rtl_path: Path, tb_path: Path | None = None) -> TaskMessage:
    ctx = {"rtl_path": str(rtl_path)}
    if tb_path:
        ctx["tb_path"] = str(tb_path)
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context=ctx,
    )


def test_sim_worker_missing_tools(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo(input logic clk, output logic [7:0] out); assign out = 8'h0; endmodule")

    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: None)

    result = worker.handle_task(make_task(rtl))

    assert result.status is TaskStatus.FAILURE
    assert "Simulation tools missing" in result.log_output


def test_sim_worker_treats_failure_marker_as_failure_even_with_zero_exit(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    tb = tmp_path / "demo_tb.sv"
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module demo_tb; initial $finish; endmodule\n")

    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, capture_output, text, timeout):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="FAILURE at cycle=4 time=37000: count=2 expected=1 rst_n=1\n",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)

    result = worker.handle_task(make_task(rtl, tb))

    assert result.status is TaskStatus.FAILURE
    assert "FAILURE at cycle=4" in result.log_output
