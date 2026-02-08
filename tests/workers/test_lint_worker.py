from __future__ import annotations

import subprocess

import pytest

from core.runtime.retry import RetryableError, TaskInputError
from core.schemas.contracts import EntityType, TaskMessage, TaskStatus, WorkerType
from workers.lint.worker import LintWorker


def test_lint_worker_missing_rtl_path():
    worker = LintWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_lint_worker_missing_file():
    worker = LintWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": "missing.sv"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_lint_worker_missing_verilator(tmp_path):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = None
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "Verilator not found" in result.log_output


def test_lint_worker_success(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_lint_worker_success_with_output(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "ok" in result.log_output


def test_lint_worker_error(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="%Error: Syntax error")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "%Error" in result.log_output


def test_lint_worker_fatal(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="%Fatal: Critical error", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "%Fatal" in result.log_output


def test_lint_worker_warning_strict_mode(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="%Warning: Unused signal", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    monkeypatch.setenv("VERILATOR_STRICT_WARNINGS", "1")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "%Warning" in result.log_output


def test_lint_worker_warning_non_strict(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="%Warning: Unused signal", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    monkeypatch.setenv("VERILATOR_STRICT_WARNINGS", "0")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "%Warning" in result.log_output

def test_lint_worker_warning_non_strict_no_output(tmp_path, monkeypatch):
    #Test that non-fatal warnings message appears when there's no output.

    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    monkeypatch.setenv("VERILATOR_STRICT_WARNINGS", "0")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "non-fatal warnings" in result.log_output

def test_lint_worker_timeout(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    with pytest.raises(RetryableError):
        worker.handle_task(task)


def test_lint_worker_subprocess_exception(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        raise Exception("Unexpected error")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "Verilator failed" in result.log_output


def test_lint_worker_multiple_rtl_paths(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path1 = tmp_path / "demo1.sv"
    rtl_path2 = tmp_path / "demo2.sv"
    rtl_path1.write_text("module demo1; endmodule\n")
    rtl_path2.write_text("module demo2; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={
            "rtl_path": str(rtl_path1),
            "rtl_paths": [str(rtl_path1), str(rtl_path2)],
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_lint_worker_missing_rtl_in_paths(tmp_path):
    worker = LintWorker(connection_params=None, stop_event=None)
    rtl_path1 = tmp_path / "demo1.sv"
    rtl_path1.write_text("module demo1; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={
            "rtl_path": str(rtl_path1),
            "rtl_paths": [str(rtl_path1), "missing.sv"],
        },
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)

def test_lint_worker_empty_rtl_paths_uses_fallback(tmp_path, monkeypatch):
    #Test that empty rtl_paths falls back to using rtl_path

    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={
            "rtl_path": str(rtl_path),
            "rtl_paths": [],
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS

def test_lint_worker_rtl_paths_with_none(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={
            "rtl_path": str(rtl_path),
            "rtl_paths": [str(rtl_path), None, ""],
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_lint_worker_combined_stdout_stderr(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl_path = tmp_path / "demo.sv"
    rtl_path.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="stdout msg", stderr="stderr msg")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "stdout msg" in result.log_output
    assert "stderr msg" in result.log_output
