from pathlib import Path

import pytest
import subprocess

from workers.lint.worker import LintWorker
from core.runtime.retry import TaskInputError
from core.schemas.contracts import TaskMessage, EntityType, WorkerType, TaskPriority, TaskStatus


def make_task(rtl_path: Path) -> TaskMessage:
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )


def test_lint_worker_missing_verilator(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    rtl.write_text(
        """module demo(input logic clk, input logic rst_n, input logic [7:0] in_data, output logic [7:0] out_data);
  assign out_data = in_data;
endmodule
"""
    )

    worker = LintWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr(worker, "verilator", None)

    result = worker.handle_task(make_task(rtl))

    assert result.status is TaskStatus.FAILURE
    assert "Verilator not found" in result.log_output


def test_lint_worker_missing_file(tmp_path):
    rtl = tmp_path / "missing.sv"
    worker = LintWorker(connection_params=None, stop_event=None)
    with pytest.raises(TaskInputError):
        worker.handle_task(make_task(rtl))


def test_lint_worker_nonfatal_warnings_are_success(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="%Warning-CMPCONST: demo.sv:1:1: warning\n")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))
    assert result.status is TaskStatus.SUCCESS
    assert "%Warning" in result.log_output


def test_lint_worker_strict_warnings_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("VERILATOR_STRICT_WARNINGS", "1")
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="%Warning-CMPCONST: demo.sv:1:1: warning\n")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))
    assert result.status is TaskStatus.FAILURE


def test_lint_worker_errors_fail(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="%Error: demo.sv:1:1: error\n")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))
    assert result.status is TaskStatus.FAILURE
