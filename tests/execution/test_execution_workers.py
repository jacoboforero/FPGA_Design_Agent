from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agents.debug.worker import DebugWorker
from agents.implementation.worker import ImplementationWorker
from agents.reflection.worker import ReflectionWorker
from agents.testbench.worker import TestbenchWorker
from core.runtime.retry import TaskInputError
from core.schemas.contracts import AgentType, EntityType, TaskMessage, TaskStatus, WorkerType
from tests.execution.helpers import FakeGateway, FakeResponse
from workers.acceptance.worker import AcceptanceWorker
from workers.distill.worker import DistillWorker
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker
from workers.tb_lint.worker import TestbenchLintWorker


def _iface_signals() -> list[dict]:
    return [
        {"name": "clk", "direction": "INPUT", "width": 1, "semantics": "clock"},
        {"name": "rst_n", "direction": "INPUT", "width": 1, "semantics": "reset"},
        {"name": "out", "direction": "OUTPUT", "width": 1, "semantics": "output"},
    ]


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts" / "task_memory").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_implementation_worker_missing_rtl_path():
    worker = ImplementationWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.IMPLEMENTATION,
        context={"node_id": "demo", "interface": {"signals": _iface_signals()}},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_implementation_worker_no_gateway(tmp_path):
    worker = ImplementationWorker(connection_params=None, stop_event=None)
    worker.gateway = None
    rtl_path = tmp_path / "demo.sv"
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.IMPLEMENTATION,
        context={"node_id": "demo", "rtl_path": str(rtl_path), "interface": {"signals": _iface_signals()}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "LLM gateway unavailable" in result.log_output


def test_implementation_worker_empty_response(tmp_path):
    worker = ImplementationWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(FakeResponse(content=" "))
    rtl_path = tmp_path / "demo.sv"
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.IMPLEMENTATION,
        context={"node_id": "demo", "rtl_path": str(rtl_path), "interface": {"signals": _iface_signals()}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "empty RTL" in result.log_output


def test_implementation_worker_success_sanitizes(tmp_path):
    worker = ImplementationWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(
        FakeResponse(
            content=(
                "module demo(input logic clk, output logic out);\n"
                "always_ff @(posedge clk) begin\n"
                "  out <= 1'b0;\n"
                "end\n"
                "endmodule\n"
            )
        )
    )
    rtl_path = tmp_path / "demo.sv"
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.IMPLEMENTATION,
        context={"node_id": "demo", "rtl_path": str(rtl_path), "interface": {"signals": _iface_signals()}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    contents = rtl_path.read_text()
    assert "always_ff" not in contents
    assert "logic" not in contents
    assert "output reg" in contents


def test_testbench_worker_missing_interface(tmp_path):
    worker = TestbenchWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.TESTBENCH,
        context={"node_id": "demo", "rtl_path": str(tmp_path / "demo.sv")},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_testbench_worker_no_gateway(tmp_path):
    worker = TestbenchWorker(connection_params=None, stop_event=None)
    worker.gateway = None
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.TESTBENCH,
        context={
            "node_id": "demo",
            "rtl_path": str(tmp_path / "demo.sv"),
            "interface": {"signals": _iface_signals()},
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "LLM gateway unavailable" in result.log_output


def test_testbench_worker_empty_response(tmp_path):
    worker = TestbenchWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(FakeResponse(content=" "))
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.TESTBENCH,
        context={
            "node_id": "demo",
            "rtl_path": str(tmp_path / "demo.sv"),
            "interface": {"signals": _iface_signals()},
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "empty testbench" in result.log_output


def test_testbench_worker_success_adds_timescale(tmp_path):
    worker = TestbenchWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(
        FakeResponse(
            content=(
                "```verilog\n"
                "module tb_demo;\n"
                "  logic clk;\n"
                "endmodule\n"
                "```\n"
            )
        )
    )
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.TESTBENCH,
        context={
            "node_id": "demo",
            "rtl_path": str(tmp_path / "demo.sv"),
            "interface": {"signals": _iface_signals()},
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    tb_path = Path(result.artifacts_path)
    contents = tb_path.read_text()
    assert contents.startswith("`timescale 1ns/1ps")
    assert "logic" not in contents
    assert "endmodule" in contents
    assert "```" not in contents


def test_testbench_worker_rewrites_invalid_dump_plusargs(tmp_path):
    worker = TestbenchWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(
        FakeResponse(
            content=(
                "module tb_demo;\n"
                "  initial begin\n"
                "    if ($value$plusargs(\"DUMP\")) $finish;\n"
                "  end\n"
                "endmodule\n"
            )
        )
    )
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.TESTBENCH,
        context={
            "node_id": "demo",
            "rtl_path": str(tmp_path / "demo.sv"),
            "interface": {"signals": _iface_signals()},
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    contents = Path(result.artifacts_path).read_text()
    assert "$test$plusargs(\"DUMP\")" in contents
    assert "$value$plusargs(\"DUMP\")" not in contents


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


def test_lint_worker_missing_file():
    worker = LintWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.LINTER,
        context={"rtl_path": "missing.sv"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_lint_worker_success(tmp_path, monkeypatch):
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


def test_tb_lint_worker_missing_tool(tmp_path):
    worker = TestbenchLintWorker(connection_params=None, stop_event=None)
    worker.iverilog = None
    rtl_path = tmp_path / "demo.sv"
    tb_path = tmp_path / "demo_tb.sv"
    rtl_path.write_text("module demo; endmodule\n")
    tb_path.write_text("module demo_tb; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.TESTBENCH_LINTER,
        context={"rtl_path": str(rtl_path), "tb_path": str(tb_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "Icarus not found" in result.log_output


def test_tb_lint_worker_missing_file(tmp_path):
    worker = TestbenchLintWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.TESTBENCH_LINTER,
        context={"rtl_path": "missing.sv", "tb_path": "missing_tb.sv"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_tb_lint_worker_success(tmp_path, monkeypatch):
    worker = TestbenchLintWorker(connection_params=None, stop_event=None)
    worker.iverilog = "iverilog"
    rtl_path = tmp_path / "demo.sv"
    tb_path = tmp_path / "demo_tb.sv"
    rtl_path.write_text("module demo; endmodule\n")
    tb_path.write_text("module demo_tb; endmodule\n")

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.tb_lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.TESTBENCH_LINTER,
        context={"rtl_path": str(rtl_path), "tb_path": str(tb_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_tb_lint_worker_semantic_failure_detects_stale_reference_compare(tmp_path, monkeypatch):
    worker = TestbenchLintWorker(connection_params=None, stop_event=None)
    worker.iverilog = "iverilog"
    rtl_path = tmp_path / "demo.sv"
    tb_path = tmp_path / "demo_tb.sv"
    rtl_path.write_text(
        "module demo(input clk, input rst_n, output reg out);\n"
        "always @(posedge clk or negedge rst_n) begin\n"
        "  if (!rst_n) out <= 1'b0;\n"
        "  else out <= ~out;\n"
        "end\n"
        "endmodule\n"
    )
    tb_path.write_text(
        "`timescale 1ns/1ps\n"
        "module tb_demo;\n"
        "  reg clk;\n"
        "  reg rst_n;\n"
        "  reg ref_out;\n"
        "  wire out;\n"
        "  demo dut(.clk(clk), .rst_n(rst_n), .out(out));\n"
        "  always #5 clk = ~clk;\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) ref_out <= 1'b0;\n"
        "    else begin\n"
        "      if (out !== ref_out) begin\n"
        "        $display(\"FAIL\");\n"
        "        $finish(1);\n"
        "      end\n"
        "      ref_out <= ~ref_out;\n"
        "    end\n"
        "  end\n"
        "  initial begin\n"
        "    clk = 1'b0;\n"
        "    rst_n = 1'b0;\n"
        "    #2 rst_n = 1'b1;\n"
        "  end\n"
        "endmodule\n"
    )

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.tb_lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.TESTBENCH_LINTER,
        context={
            "rtl_path": str(rtl_path),
            "tb_path": str(tb_path),
            "clocking": {
                "clock_name": "clk",
                "clock_polarity": "POSEDGE",
                "reset_name": "rst_n",
                "reset_polarity": "ACTIVE_LOW",
            },
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "TBSEM004" in result.log_output


def test_tb_lint_worker_delay_semantic_ignores_comment_tokens_and_allows_two_delays(tmp_path, monkeypatch):
    worker = TestbenchLintWorker(connection_params=None, stop_event=None)
    worker.iverilog = "iverilog"
    rtl_path = tmp_path / "demo.sv"
    tb_path = tmp_path / "demo_tb.sv"
    rtl_path.write_text(
        "module demo(input clk, input rst_n, input en, output reg out);\n"
        "always @(posedge clk or negedge rst_n) begin\n"
        "  if (!rst_n) out <= 1'b0;\n"
        "  else if (en) out <= ~out;\n"
        "end\n"
        "endmodule\n"
    )
    tb_path.write_text(
        "`timescale 1ns/1ps\n"
        "module tb_demo;\n"
        "  reg clk;\n"
        "  reg rst_n;\n"
        "  reg en;\n"
        "  reg exp_out;\n"
        "  wire out;\n"
        "  demo dut(.clk(clk), .rst_n(rst_n), .en(en), .out(out));\n"
        "  always #5 clk = ~clk;\n"
        "  initial begin clk = 1'b0; rst_n = 1'b0; en = 1'b0; #2 rst_n = 1'b1; #10 en = 1'b1; end\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    #1;\n"
        "    if (!rst_n) begin\n"
        "      exp_out <= 1'b0;\n"
        "    end else begin\n"
        "      if (en) exp_out = ~exp_out;\n"
        "      // (c) wait #1 for settle\n"
        "      #1;\n"
        "      if (out !== exp_out) begin\n"
        "        $display(\"FAIL\");\n"
        "        $finish(1);\n"
        "      end\n"
        "      exp_out <= exp_out;\n"
        "    end\n"
        "  end\n"
        "endmodule\n"
    )

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.tb_lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.TESTBENCH_LINTER,
        context={
            "rtl_path": str(rtl_path),
            "tb_path": str(tb_path),
            "clocking": [
                {
                    "clock_name": "clk",
                    "clock_polarity": "POSEDGE",
                    "reset_name": "rst_n",
                    "reset_polarity": "ACTIVE_LOW",
                }
            ],
            "interface": {
                "signals": [
                    {"name": "clk"},
                    {"name": "rst_n"},
                    {"name": "en"},
                    {"name": "out"},
                ]
            },
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "TBSEM006" not in result.log_output


def test_tb_lint_worker_semantic_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("TB_LINT_SEMANTIC", "0")
    worker = TestbenchLintWorker(connection_params=None, stop_event=None)
    worker.iverilog = "iverilog"
    rtl_path = tmp_path / "demo.sv"
    tb_path = tmp_path / "demo_tb.sv"
    rtl_path.write_text("module demo(input clk, input rst_n, output reg out); endmodule\n")
    tb_path.write_text(
        "module tb_demo;\n"
        "  reg clk;\n"
        "  reg rst_n;\n"
        "  reg ref_out;\n"
        "  wire out;\n"
        "  demo dut(.clk(clk), .rst_n(rst_n), .out(out));\n"
        "  always #5 clk = ~clk;\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) ref_out <= 1'b0;\n"
        "    else begin\n"
        "      if (out !== ref_out) begin\n"
        "        $display(\"FAIL\");\n"
        "        $finish(1);\n"
        "      end\n"
        "      ref_out <= ~ref_out;\n"
        "    end\n"
        "  end\n"
        "  initial begin clk = 1'b0; rst_n = 1'b0; #2 rst_n = 1'b1; end\n"
        "endmodule\n"
    )

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr("workers.tb_lint.worker.subprocess.run", fake_run)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.TESTBENCH_LINTER,
        context={"rtl_path": str(rtl_path), "tb_path": str(tb_path)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "TBSEM004" not in result.log_output


def test_acceptance_worker_no_requirements(sandbox):
    worker = AcceptanceWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.ACCEPTANCE,
        context={"node_id": "demo", "acceptance": {}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "No acceptance criteria" in result.log_output


def test_acceptance_worker_missing_artifact(sandbox):
    worker = AcceptanceWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.ACCEPTANCE,
        context={
            "node_id": "demo",
            "acceptance": {"required_artifacts": [{"name": "lint_report", "mandatory": True}]},
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "Missing required artifact" in result.log_output


def test_acceptance_worker_metric_passes(sandbox):
    worker = AcceptanceWorker(connection_params=None, stop_event=None)
    report = Path("artifacts/task_memory/demo/sim/coverage_report.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"metrics": {"branch": 0.9}}))
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.ACCEPTANCE,
        context={
            "node_id": "demo",
            "acceptance": {
                "acceptance_metrics": [
                    {
                        "metric_id": "branch",
                        "operator": ">=",
                        "target_value": "0.8",
                        "metric_source": "coverage_report",
                    }
                ]
            },
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS


def test_acceptance_worker_relaxes_coverage_when_sim_passes(sandbox):
    worker = AcceptanceWorker(connection_params=None, stop_event=None)
    sim_log = Path("artifacts/task_memory/demo/sim/log.txt")
    sim_log.parent.mkdir(parents=True, exist_ok=True)
    sim_log.write_text("PASS: All checks passed at cycle=1 time=10\n")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.ACCEPTANCE,
        context={
            "node_id": "demo",
            "acceptance": {
                "required_artifacts": [
                    {"name": "coverage_report", "mandatory": True},
                ],
                "acceptance_metrics": [
                    {
                        "metric_id": "branch",
                        "operator": ">=",
                        "target_value": "0.8",
                        "metric_source": "coverage_report",
                    }
                ],
            },
        },
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert "coverage gating deferred" in result.log_output


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


def test_distill_worker_missing_node_id():
    worker = DistillWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.DISTILLATION,
        context={},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_distill_worker_missing_sim_log(sandbox):
    worker = DistillWorker(connection_params=None, stop_event=None)
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.DISTILLATION,
        context={"node_id": "demo"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_distill_worker_success_extracts_failure(sandbox):
    worker = DistillWorker(connection_params=None, stop_event=None)
    sim_log = Path("artifacts/task_memory/demo/sim/log.txt")
    sim_log.parent.mkdir(parents=True, exist_ok=True)
    sim_log.write_text("FAIL: cycle=5 time=50")
    waveform = Path("artifacts/task_memory/demo/sim/waveform.vcd")
    waveform.write_text("vcd")
    task = TaskMessage(
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.DISTILLATION,
        context={"node_id": "demo"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    distilled = Path("artifacts/task_memory/demo/distill/distilled_dataset.json").read_text()
    payload = json.loads(distilled)
    assert payload["failure_cycle"] == 5
    assert payload["waveform_path"] == str(waveform)


def test_reflection_worker_missing_distill(sandbox):
    worker = ReflectionWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(FakeResponse(content="{}"))
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.REFLECTION,
        context={"node_id": "demo", "coverage_goals": {}},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_reflection_worker_invalid_json(sandbox):
    worker = ReflectionWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(FakeResponse(content="not json"))
    distill = Path("artifacts/task_memory/demo/distill/distilled_dataset.json")
    distill.parent.mkdir(parents=True, exist_ok=True)
    distill.write_text("{}")
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.REFLECTION,
        context={"node_id": "demo", "coverage_goals": {}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "valid JSON" in result.log_output


def test_reflection_worker_success(sandbox):
    worker = ReflectionWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(
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
    distill = Path("artifacts/task_memory/demo/distill/distilled_dataset.json")
    distill.parent.mkdir(parents=True, exist_ok=True)
    distill.write_text("{}")
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.REFLECTION,
        context={"node_id": "demo", "coverage_goals": {}},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert result.reflection_insights


def test_debug_worker_missing_rtl_path_raises(sandbox):
    worker = DebugWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(FakeResponse(content="{}"))
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.DEBUG,
        context={"node_id": "demo"},
    )
    with pytest.raises(TaskInputError):
        worker.handle_task(task)


def test_debug_worker_invalid_json(sandbox):
    worker = DebugWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(FakeResponse(content="not json"))
    rtl = Path("demo.sv")
    tb = Path("demo_tb.sv")
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module tb_demo; initial $finish; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.DEBUG,
        context={"node_id": "demo", "rtl_path": str(rtl), "tb_path": str(tb)},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "valid JSON" in result.log_output


def test_debug_worker_retries_until_valid_json(sandbox, monkeypatch):
    class SequenceGateway:
        def __init__(self, responses):
            self.responses = responses
            self.calls = 0

        async def generate(self, messages, config):
            resp = self.responses[self.calls]
            self.calls += 1
            return resp

    worker = DebugWorker(connection_params=None, stop_event=None)
    monkeypatch.setenv("DEBUG_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("IVERILOG_PATH", "iverilog")
    monkeypatch.setenv("VERILATOR_PATH", "verilator")

    def fake_run(cmd, timeout_s):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("agents.debug.worker._run_subprocess", fake_run)
    monkeypatch.setattr("agents.debug.worker.shutil.which", lambda name: f"/bin/{name}")
    rtl = Path("demo.sv")
    tb = Path("demo_tb.sv")
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module tb_demo; initial $finish; endmodule\n")
    worker.gateway = SequenceGateway(
        [
            FakeResponse(content="not json"),
            FakeResponse(content="still not json"),
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
            ),
        ]
    )
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.DEBUG,
        context={"node_id": "demo", "rtl_path": str(rtl), "tb_path": str(tb), "attempt": 1},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert worker.gateway.calls == 3


def test_debug_worker_success(sandbox, monkeypatch):
    monkeypatch.setenv("IVERILOG_PATH", "iverilog")
    monkeypatch.setenv("VERILATOR_PATH", "verilator")

    def fake_run(cmd, timeout_s):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("agents.debug.worker._run_subprocess", fake_run)
    monkeypatch.setattr("agents.debug.worker.shutil.which", lambda name: f"/bin/{name}")

    worker = DebugWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(
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
    rtl = Path("demo.sv")
    tb = Path("demo_tb.sv")
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module tb_demo; initial $finish; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.DEBUG,
        context={"node_id": "demo", "rtl_path": str(rtl), "tb_path": str(tb), "attempt": 1},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert result.reflections
    assert "Local validation passed" in result.log_output


def test_debug_worker_local_validation_failure(sandbox, monkeypatch):
    monkeypatch.setenv("DEBUG_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("IVERILOG_PATH", "iverilog")
    monkeypatch.setenv("VERILATOR_PATH", "verilator")
    monkeypatch.setattr("agents.debug.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, timeout_s):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="tb syntax error")

    monkeypatch.setattr("agents.debug.worker._run_subprocess", fake_run)

    worker = DebugWorker(connection_params=None, stop_event=None)
    worker.gateway = FakeGateway(
        FakeResponse(
            content=json.dumps(
                {
                    "summary": "fix tb",
                    "touched_files": ["tb"],
                    "rtl_lines": None,
                    "tb_lines": ["module tb_demo;", "  initial $finish;", "endmodule"],
                    "risks": [],
                    "next_steps": ["retry"],
                }
            )
        )
    )
    rtl = Path("demo.sv")
    tb = Path("demo_tb.sv")
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module tb_demo; initial $finish; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.DEBUG,
        context={"node_id": "demo", "rtl_path": str(rtl), "tb_path": str(tb), "attempt": 1, "debug_reason": "tb_lint"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.FAILURE
    assert "local validation failed" in result.log_output.lower()
    assert "tb_lint=FAIL" in result.log_output


def test_debug_worker_local_validation_retry_then_success(sandbox, monkeypatch):
    class SequenceGateway:
        def __init__(self, responses):
            self.responses = responses
            self.calls = 0

        async def generate(self, messages, config):
            resp = self.responses[self.calls]
            self.calls += 1
            return resp

    monkeypatch.setenv("DEBUG_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("IVERILOG_PATH", "iverilog")
    monkeypatch.setenv("VERILATOR_PATH", "verilator")
    monkeypatch.setattr("agents.debug.worker.shutil.which", lambda name: f"/bin/{name}")

    calls = {"n": 0}

    def fake_run(cmd, timeout_s):
        calls["n"] += 1
        if calls["n"] == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="tb syntax error")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("agents.debug.worker._run_subprocess", fake_run)

    payload = json.dumps(
        {
            "summary": "fix tb",
            "touched_files": ["tb"],
            "rtl_lines": None,
            "tb_lines": ["module tb_demo;", "  initial $finish;", "endmodule"],
            "risks": [],
            "next_steps": ["retry"],
        }
    )
    worker = DebugWorker(connection_params=None, stop_event=None)
    worker.gateway = SequenceGateway([FakeResponse(content=payload), FakeResponse(content=payload)])
    rtl = Path("demo.sv")
    tb = Path("demo_tb.sv")
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module tb_demo; initial $finish; endmodule\n")
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.DEBUG,
        context={"node_id": "demo", "rtl_path": str(rtl), "tb_path": str(tb), "attempt": 1, "debug_reason": "tb_lint"},
    )
    result = worker.handle_task(task)
    assert result.status is TaskStatus.SUCCESS
    assert worker.gateway.calls == 2
    assert "Local validation passed" in result.log_output
