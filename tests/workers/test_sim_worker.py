from pathlib import Path
import subprocess

import pytest

from core.tools.registry import CommandSpec, LintConfig, SimulationConfig, ToolRegistry, ToolSpec
from workers.sim.worker import SimulationWorker
from core.schemas.contracts import TaskMessage, EntityType, WorkerType, TaskPriority, TaskStatus


def make_task(
    rtl_path: Path,
    tb_path: Path | None = None,
    oracle_ref_path: Path | None = None,
    verification_scope: str | None = None,
    execution_policy: dict | None = None,
    node_id: str | None = None,
) -> TaskMessage:
    ctx = {"rtl_path": str(rtl_path)}
    if tb_path:
        ctx["tb_path"] = str(tb_path)
    if oracle_ref_path:
        ctx["oracle_ref_path"] = str(oracle_ref_path)
    if verification_scope:
        ctx["verification_scope"] = verification_scope
    if execution_policy:
        ctx["execution_policy"] = execution_policy
    if node_id:
        ctx["node_id"] = node_id
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.HEAVY_DETERMINISTIC,
        task_type=WorkerType.SIMULATOR,
        context=ctx,
    )


def _registry_with_sim_tools(
    *,
    iverilog_path: str = "/registry/iverilog",
    vvp_path: str = "/registry/vvp",
    build_timeout_s: int = 23,
    run_timeout_s: int = 29,
    dump_timeout_s: int = 31,
) -> ToolRegistry:
    return ToolRegistry(
        tools={
            "iverilog": ToolSpec(
                name="iverilog",
                resolved_path=iverilog_path,
                commands={
                    "build": CommandSpec(
                        template="{tool} --build -o {output} {sources}",
                        timeout_seconds=build_timeout_s,
                    )
                },
                capabilities={},
            ),
            "vvp": ToolSpec(
                name="vvp",
                resolved_path=vvp_path,
                commands={
                    "run": CommandSpec(
                        template="{tool} --run {binary}",
                        timeout_seconds=run_timeout_s,
                    ),
                    "run_with_dump": CommandSpec(
                        template="{tool} --dump {binary} +DUMP +DUMP_FILE={waveform_path} {window_args}",
                        timeout_seconds=dump_timeout_s,
                    ),
                },
                capabilities={"supports_dump": True},
            ),
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


def test_sim_worker_missing_tools(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo(input logic clk, output logic [7:0] out); assign out = 8'h0; endmodule")

    worker = SimulationWorker(connection_params=None, stop_event=None, registry=_empty_registry())
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

    def fake_run(cmd, **kwargs):
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


def test_sim_worker_includes_oracle_reference_in_compile_sources(tmp_path, monkeypatch):
    rtl = tmp_path / "TopModule.sv"
    tb = tmp_path / "Prob001_test.sv"
    ref = tmp_path / "Prob001_ref.sv"
    rtl.write_text("module TopModule; endmodule\n")
    tb.write_text("module tb; TopModule dut(); RefModule ref_i(); endmodule\n")
    ref.write_text("module RefModule; endmodule\n")

    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="PASS\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)

    result = worker.handle_task(make_task(rtl, tb, ref))

    assert result.status is TaskStatus.SUCCESS
    compile_cmd = calls[0]
    assert str(tb) in compile_cmd
    assert str(ref) in compile_cmd


def test_sim_worker_benchmark_mode_fails_nonzero_mismatch_with_zero_exit(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    tb = tmp_path / "demo_tb.sv"
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module demo_tb; initial $finish; endmodule\n")

    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, **kwargs):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="Mismatches: 3 in 41 samples\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)

    result = worker.handle_task(make_task(rtl, tb, verification_scope="oracle_compare"))

    assert result.status is TaskStatus.FAILURE
    assert "nonzero mismatches=3" in result.log_output


def test_sim_worker_benchmark_mode_fails_timeout_marker_with_zero_exit(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    tb = tmp_path / "demo_tb.sv"
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module demo_tb; initial $finish; endmodule\n")

    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, **kwargs):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="TIMEOUT\nMismatches: 0 in 41 samples\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)

    result = worker.handle_task(make_task(rtl, tb, verification_scope="oracle_compare"))

    assert result.status is TaskStatus.FAILURE
    assert "timeout reported by benchmark harness" in result.log_output


def test_sim_worker_benchmark_mode_passes_zero_mismatches(tmp_path, monkeypatch):
    rtl = tmp_path / "demo.sv"
    tb = tmp_path / "demo_tb.sv"
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module demo_tb; initial $finish; endmodule\n")

    worker = SimulationWorker(connection_params=None, stop_event=None)
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(cmd, **kwargs):
        if cmd[0].endswith("iverilog"):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[0].endswith("vvp"):
            return subprocess.CompletedProcess(cmd, 0, stdout="Mismatches: 0 in 41 samples\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)

    result = worker.handle_task(make_task(rtl, tb, verification_scope="oracle_compare"))

    assert result.status is TaskStatus.SUCCESS


def test_sim_worker_uses_registry_commands_and_timeouts(tmp_path, monkeypatch):
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda _name: None)
    worker = SimulationWorker(
        connection_params=None,
        stop_event=None,
        registry=_registry_with_sim_tools(),
    )

    rtl = tmp_path / "demo.sv"
    rtl.write_text("module demo; endmodule\n")

    calls: list[tuple[list[str], float]] = []

    def fake_run(cmd, **kwargs):
        calls.append((list(cmd), float(kwargs["timeout"])))
        return subprocess.CompletedProcess(cmd, 0, stdout="PASS", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl))

    assert result.status is TaskStatus.SUCCESS
    assert calls[0][0][0] == "/registry/iverilog"
    assert calls[0][0][1] == "--build"
    assert calls[0][1] == 23
    assert calls[1][0][0] == "/registry/vvp"
    assert calls[1][0][1] == "--run"
    assert calls[1][1] == 29


def test_sim_worker_uses_registry_dump_command_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("workers.sim.worker.shutil.which", lambda _name: None)
    worker = SimulationWorker(
        connection_params=None,
        stop_event=None,
        registry=_registry_with_sim_tools(),
    )
    rtl = tmp_path / "demo.sv"
    tb = tmp_path / "demo_tb.sv"
    rtl.write_text("module demo; endmodule\n")
    tb.write_text("module demo_tb; initial $finish; endmodule\n")

    calls: list[tuple[list[str], float]] = []

    def fake_run(cmd, **kwargs):
        cmd_list = list(cmd)
        calls.append((cmd_list, float(kwargs["timeout"])))
        if "--build" in cmd_list:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if "--run" in cmd_list:
            return subprocess.CompletedProcess(cmd, 1, stdout="FAIL: cycle=12 time=120", stderr="")
        if "--dump" in cmd_list:
            dump_arg = next((arg for arg in cmd_list if arg.startswith("+DUMP_FILE=")), "")
            dump_path = Path(dump_arg.split("=", 1)[1]) if dump_arg else None
            if dump_path:
                dump_path.parent.mkdir(parents=True, exist_ok=True)
                dump_path.write_text("vcd")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("workers.sim.worker.subprocess.run", fake_run)
    result = worker.handle_task(make_task(rtl, tb, node_id="demo"))

    assert result.status is TaskStatus.FAILURE
    dump_calls = [call for call in calls if "--dump" in call[0]]
    assert dump_calls
    assert dump_calls[0][0][0] == "/registry/vvp"
    assert dump_calls[0][1] == 31
