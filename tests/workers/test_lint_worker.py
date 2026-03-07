from pathlib import Path

import pytest
import subprocess

from core.tools.registry import CommandSpec, LintConfig, SimulationConfig, ToolRegistry, ToolSpec
from workers.lint.worker import LintWorker
from core.runtime.retry import TaskInputError
from core.runtime.config import get_runtime_config, set_runtime_config
from core.schemas.contracts import TaskMessage, EntityType, WorkerType, TaskPriority, TaskStatus


def make_task(rtl_path: Path) -> TaskMessage:
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )


def _registry_with_verilator(path: str = "/registry/verilator", timeout_s: int = 17) -> ToolRegistry:
    return ToolRegistry(
        tools={
            "verilator": ToolSpec(
                name="verilator",
                resolved_path=path,
                commands={
                    "lint": CommandSpec(
                        template="{tool} --lint-only --quiet --sv {sources}",
                        timeout_seconds=timeout_s,
                    )
                },
                capabilities={"error_marker": "%Error", "fatal_marker": "%Fatal"},
            )
        },
        simulation=SimulationConfig(
            artifact_base="artifacts/task_memory",
            waveform_filename="waveform.vcd",
            fail_window_before=20,
            fail_window_after=5,
        ),
        lint=LintConfig(strict_warnings=False),
    )


def _empty_registry() -> ToolRegistry:
    return ToolRegistry(
        tools={},
        simulation=SimulationConfig(
            artifact_base="artifacts/task_memory",
            waveform_filename="waveform.vcd",
            fail_window_before=20,
            fail_window_after=5,
        ),
        lint=LintConfig(strict_warnings=False),
    )


def test_lint_worker_missing_verilator(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    rtl.write_text(
        """module demo(input logic clk, input logic rst_n, input logic [7:0] in_data, output logic [7:0] out_data);
  assign out_data = in_data;
endmodule
"""
    )

    worker = LintWorker(connection_params=None, stop_event=None, registry=_empty_registry())
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
    cfg = get_runtime_config().model_copy(deep=True)
    cfg.lint.verilator_strict_warnings = True
    set_runtime_config(cfg)
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


def test_lint_worker_moddup_warning_fails_by_default(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="",
            stderr="%Warning-MODDUP: demo.sv:1:1: Duplicate declaration of module: 'demo'\n",
        )

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))
    assert result.status is TaskStatus.FAILURE
    assert "MODDUP" in result.log_output


def test_lint_worker_retries_without_quiet_when_unsupported(tmp_path, monkeypatch):
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(list(cmd))
        if "--quiet" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="%Error: Invalid option: --quiet\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))
    assert result.status is TaskStatus.SUCCESS
    assert any("--quiet" in cmd for cmd in calls)
    assert any("--quiet" not in cmd for cmd in calls)
    assert "retried without it" in result.log_output.lower()


def test_lint_worker_semantic_fail_for_combinational_edge_always(tmp_path, monkeypatch):
    cfg = get_runtime_config().model_copy(deep=True)
    cfg.lint.rtl_semantic_enabled = True
    cfg.lint.rtl_semantic_strict = True
    set_runtime_config(cfg)
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "cmp.sv"
    rtl.write_text(
        """module cmp(input clk, input [7:0] a, input [7:0] b, output reg y);
always @(posedge clk) begin
  y <= (a < b);
end
endmodule
"""
    )

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl), "module_contract": {"style": "combinational", "forbid_edge_always": True}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "RLSEM001" in result.log_output


def test_lint_worker_semantic_warn_in_non_strict_mode(tmp_path, monkeypatch):
    cfg = get_runtime_config().model_copy(deep=True)
    cfg.lint.rtl_semantic_enabled = True
    cfg.lint.rtl_semantic_strict = False
    set_runtime_config(cfg)
    worker = LintWorker(connection_params=None, stop_event=None)
    worker.verilator = "verilator"
    rtl = tmp_path / "cmp.sv"
    rtl.write_text(
        """module cmp(input clk, input [7:0] a, input [7:0] b, output reg y);
always @(posedge clk) begin
  y <= (a < b);
end
endmodule
"""
    )

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl), "module_contract": {"style": "combinational", "forbid_edge_always": True}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "[rtl_semantic] WARN" in result.log_output


def test_lint_worker_uses_registry_tool_path_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("workers.lint.worker.shutil.which", lambda _name: None)
    worker = LintWorker(
        connection_params=None,
        stop_event=None,
        registry=_registry_with_verilator(timeout_s=19),
    )
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")

    calls: list[tuple[list[str], float]] = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append((list(cmd), timeout))
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.lint.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))

    assert result.status is TaskStatus.SUCCESS
    assert calls
    assert calls[0][0][0] == "/registry/verilator"
    assert calls[0][1] == 19
