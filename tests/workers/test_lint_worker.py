from pathlib import Path

import pytest

from workers.lint.worker import LintWorker
from core.schemas.contracts import TaskMessage, EntityType, WorkerType, TaskPriority


def make_task(rtl_path: Path) -> TaskMessage:
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": str(rtl_path)},
    )


def test_lint_worker_fallback_without_verilator(tmp_path, monkeypatch):
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

    assert result.status.value == "SUCCESS"
    assert "Mock lint passed" in result.log_output


def test_lint_worker_missing_file(tmp_path):
    rtl = tmp_path / "missing.sv"
    worker = LintWorker(connection_params=None, stop_event=None)
    result = worker.handle_task(make_task(rtl))
    assert result.status.value == "FAILURE"
    assert "RTL missing" in result.log_output
