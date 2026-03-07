from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
from pathlib import Path

import pytest

import apps.cli.run_verilog_eval as run_verilog_eval
from apps.cli.run_verilog_eval import (
    PromptCase,
    _assert_generated_interface_matches,
    _bind_benchmark_oracle_assets,
    _discover_prompt_cases,
    _ensure_framework,
    _load_oracle_manifest,
    _run_official_analyze,
    _script_cmd,
    _run_mode,
    _run_sample_test,
    _write_generate_log,
    _resolve_target_interface,
    _resolve_target_module_name,
    _isolated_task_memory,
    _summary_metrics,
    _summary_rows,
    build_parser,
    run_from_args,
)
from core.runtime.config import load_runtime_config


def test_summary_metrics_parses_official_kv_lines(tmp_path: Path):
    summary_txt = tmp_path / "summary.txt"
    summary_txt.write_text(
        "\n".join(
            [
                "pass_rate = 0.375",
                "nproblems = 80",
                "nsamples = 20",
                "tokens = 12345",
                "ignored: text",
            ]
        )
        + "\n"
    )
    metrics = _summary_metrics(summary_txt)
    assert metrics["pass_rate"] == 0.375
    assert metrics["nproblems"] == 80
    assert metrics["nsamples"] == 20
    assert metrics["tokens"] == 12345


def test_summary_rows_parses_problem_rows(tmp_path: Path):
    summary_csv = tmp_path / "summary.csv"
    summary_csv.write_text(
        "\n".join(
            [
                "Prob001,1,1,1.0,P",
                "Prob002,0,1,0.0,S",
            ]
        )
        + "\n"
    )
    rows = _summary_rows(summary_csv)
    assert len(rows) == 2
    assert rows[0]["problem_id"] == "Prob001"
    assert rows[0]["npass"] == "1"
    assert rows[1]["problem_id"] == "Prob002"


def test_script_cmd_uses_python3_for_env_python_when_python_missing(tmp_path: Path, monkeypatch):
    script = tmp_path / "sv-iv-analyze"
    script.write_text("#!/usr/bin/env python\nprint('ok')\n", encoding="utf-8")
    script.chmod(0o755)

    monkeypatch.setattr("apps.cli.run_verilog_eval.shutil.which", lambda name: None if name == "python" else "/usr/bin/python3")
    cmd = _script_cmd(script, ["--csv=summary.csv"])
    assert cmd[:2] == ["python3", str(script)]


def test_script_cmd_keeps_executable_when_python_available(tmp_path: Path, monkeypatch):
    script = tmp_path / "sv-iv-analyze"
    script.write_text("#!/usr/bin/env python\nprint('ok')\n", encoding="utf-8")
    script.chmod(0o755)

    monkeypatch.setattr("apps.cli.run_verilog_eval.shutil.which", lambda name: "/usr/bin/python" if name == "python" else "/usr/bin/python3")
    cmd = _script_cmd(script, ["--csv=summary.csv"])
    assert cmd[0] == str(script)


def test_discover_prompt_cases_maps_official_prompts_to_dataset(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()

    (prompts_dir / "Prob079_fsm3onehot_prompt.txt").write_text("prompt A\n")
    (prompts_dir / "Prob020_mt2015_eq2_prompt.txt").write_text("prompt B\n")
    (prompts_dir / "readme.txt").write_text("not a problem prompt\n")
    (prompts_dir / "problems.txt").write_text("Prob020_mt2015_eq2\nProb079_fsm3onehot\n")

    (dataset_dir / "Prob079_test.sv").write_text("module tb; endmodule\n")
    (dataset_dir / "Prob079_ref.sv").write_text("module ref; endmodule\n")
    (dataset_dir / "Prob020_test.sv").write_text("module tb; endmodule\n")
    (dataset_dir / "Prob020_ref.sv").write_text("module ref; endmodule\n")

    cases = _discover_prompt_cases(
        prompts_dir=prompts_dir,
        dataset_dir=dataset_dir,
        only_problem=[],
        max_problems=0,
    )
    assert [case.problem_id for case in cases] == ["Prob020", "Prob079"]
    assert cases[0].prompt_path.name == "Prob020_mt2015_eq2_prompt.txt"
    assert cases[1].prompt_path.name == "Prob079_fsm3onehot_prompt.txt"


def test_discover_prompt_cases_prefers_official_prompt_names(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()

    (prompts_dir / "Prob079_fsm3onehot_prompt.txt").write_text("official prompt\n")
    (prompts_dir / "Prob079_fsm3onehot.txt").write_text("legacy prompt\n")
    (dataset_dir / "Prob079_test.sv").write_text("module tb; endmodule\n")
    (dataset_dir / "Prob079_ref.sv").write_text("module ref; endmodule\n")

    cases = _discover_prompt_cases(
        prompts_dir=prompts_dir,
        dataset_dir=dataset_dir,
        only_problem=[],
        max_problems=0,
    )
    assert len(cases) == 1
    assert cases[0].prompt_path.name == "Prob079_fsm3onehot_prompt.txt"


def test_discover_prompt_cases_falls_back_to_legacy_prompt_names(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()

    (prompts_dir / "Prob079_fsm3onehot.txt").write_text("prompt A\n")
    (dataset_dir / "Prob079_fsm3onehot_test.sv").write_text("module tb; endmodule\n")
    (dataset_dir / "Prob079_fsm3onehot_ref.sv").write_text("module ref; endmodule\n")

    cases = _discover_prompt_cases(
        prompts_dir=prompts_dir,
        dataset_dir=dataset_dir,
        only_problem=[],
        max_problems=0,
    )
    assert len(cases) == 1
    assert cases[0].problem_id == "Prob079"
    assert cases[0].test_sv.name == "Prob079_fsm3onehot_test.sv"
    assert cases[0].ref_sv.name == "Prob079_fsm3onehot_ref.sv"


def test_discover_prompt_cases_missing_requested_problem_raises(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()
    (prompts_dir / "Prob001_demo.txt").write_text("prompt\n")
    (dataset_dir / "Prob001_test.sv").write_text("module tb; endmodule\n")
    (dataset_dir / "Prob001_ref.sv").write_text("module ref; endmodule\n")

    with pytest.raises(RuntimeError, match="Requested problem IDs not found"):
        _discover_prompt_cases(
            prompts_dir=prompts_dir,
            dataset_dir=dataset_dir,
            only_problem=["Prob001", "Prob079"],
            max_problems=0,
        )


def test_discover_prompt_cases_uses_oracle_manifest(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()

    (prompts_dir / "Prob010_demo_prompt.txt").write_text("prompt\n")
    (dataset_dir / "custom" / "p10_test.sv").parent.mkdir(parents=True)
    (dataset_dir / "custom" / "p10_test.sv").write_text("module tb; endmodule\n")
    (dataset_dir / "custom" / "p10_ref.sv").write_text("module ref; endmodule\n")

    manifest_path = tmp_path / "oracle_manifest.json"
    manifest_path.write_text(
        '{"Prob010": {"test_sv": "custom/p10_test.sv", "ref_sv": "custom/p10_ref.sv"}}\n'
    )
    manifest = _load_oracle_manifest(manifest_path)
    cases = _discover_prompt_cases(
        prompts_dir=prompts_dir,
        dataset_dir=dataset_dir,
        only_problem=[],
        max_problems=0,
        oracle_manifest=manifest,
    )
    assert len(cases) == 1
    assert cases[0].test_sv.name == "p10_test.sv"
    assert cases[0].ref_sv.name == "p10_ref.sv"


def test_ensure_framework_accepts_official_layout_without_sv_iv_test(tmp_path: Path):
    root = tmp_path / "verilog_eval"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "sv-iv-analyze").write_text("#!/usr/bin/env bash\n")
    (root / "Makefile.in").write_text("all:\n")
    (root / "dataset_spec-to-rtl").mkdir()

    dataset_dir = _ensure_framework(root)
    assert dataset_dir == root / "dataset_spec-to-rtl"


def test_run_sample_test_writes_timeout_marker(tmp_path: Path, monkeypatch):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("prompt\n")
    test_sv.write_text("module tb; endmodule\n")
    ref_sv.write_text("module ref; endmodule\n")

    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)
    sample_dir = tmp_path / "out" / "Prob001"
    sample_dir.mkdir(parents=True)
    (sample_dir / "Prob001_sample01.sv").write_text("module Prob001(); endmodule\n")

    calls = []

    def fake_run_cmd(cmd, *, cwd, timeout_s=300):  # noqa: ANN001
        calls.append((cmd, cwd, timeout_s))
        if cmd[0] == "iverilog_bin":
            return subprocess.CompletedProcess(cmd, 0, stdout="compile ok\n", stderr="")
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_s, output="partial run output\n", stderr="")

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_cmd", fake_run_cmd)

    _run_sample_test(
        case=case,
        sample_index=1,
        sample_dir=sample_dir,
        iverilog_bin="iverilog_bin",
        vvp_bin="vvp_bin",
    )

    iv_log = sample_dir / "Prob001_sample01-sv-iv-test.log"
    text = iv_log.read_text()
    assert "compile ok" in text
    assert "partial run output" in text
    assert "TIMEOUT" in text
    assert calls[0][0][0] == "iverilog_bin"
    assert calls[1][0][0] == "vvp_bin"


def test_run_official_analyze_auto_discovers_problem_dirs(tmp_path: Path, monkeypatch):
    root = tmp_path / "verilog_eval"
    build_dir = tmp_path / "build"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "sv-iv-analyze").write_text("#!/usr/bin/env bash\n")
    build_dir.mkdir()
    captured = {}

    def fake_run_cmd(cmd, *, cwd, timeout_s=300):  # noqa: ANN001
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        summary_csv = cwd / "summary.csv"
        summary_csv.write_text("Prob001,1,1,1.0,.\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="pass_rate = 1.0\n", stderr="")

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_cmd", fake_run_cmd)

    summary_txt, summary_csv = _run_official_analyze(root, build_dir)
    assert summary_txt.exists()
    assert summary_csv.exists()
    assert "Prob*" not in captured["cmd"]


def test_resolve_target_module_name_prefers_testbench_instance(tmp_path: Path):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("I would like you to implement a module named WrongName.\n")
    test_sv.write_text(
        "\n".join(
            [
                "module tb();",
                "  TopModule top_module1();",
                "endmodule",
            ]
        )
        + "\n"
    )
    ref_sv.write_text("module RefModule(); endmodule\n")
    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)
    assert _resolve_target_module_name(case, prompt_path.read_text()) == "TopModule"


def test_resolve_target_module_name_falls_back_to_prompt_text(tmp_path: Path):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("Please implement a module named FancyTop.\n")
    test_sv.write_text("module tb(); endmodule\n")
    ref_sv.write_text("module RefModule(); endmodule\n")
    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)
    assert _resolve_target_module_name(case, prompt_path.read_text()) == "FancyTop"


def test_resolve_target_interface_parses_ref_module_ports(tmp_path: Path):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("prompt\n")
    test_sv.write_text("module tb(); endmodule\n")
    ref_sv.write_text(
        "\n".join(
            [
                "module RefModule (",
                "  input clk,",
                "  input [7:0] in_a,",
                "  output [7:0] out_z",
                ");",
                "endmodule",
            ]
        )
        + "\n"
    )
    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)
    signals = _resolve_target_interface(case)
    assert signals == [
        {"name": "clk", "direction": "INPUT", "width": 1},
        {"name": "in_a", "direction": "INPUT", "width": 8},
        {"name": "out_z", "direction": "OUTPUT", "width": 8},
    ]


def test_assert_generated_interface_matches_accepts_matching_interface(tmp_path: Path):
    rtl_path = tmp_path / "TopModule.sv"
    rtl_path.write_text(
        "\n".join(
            [
                "module TopModule (",
                "  output zero",
                ");",
                "  assign zero = 1'b0;",
                "endmodule",
            ]
        )
        + "\n"
    )
    _assert_generated_interface_matches(
        rtl_path=rtl_path,
        module_name="TopModule",
        expected_signals=[{"name": "zero", "direction": "OUTPUT", "width": 1}],
    )


def test_assert_generated_interface_matches_rejects_extra_ports(tmp_path: Path):
    rtl_path = tmp_path / "TopModule.sv"
    rtl_path.write_text(
        "\n".join(
            [
                "module TopModule (",
                "  output reg zero,",
                "  input clk",
                ");",
                "always @(posedge clk) zero <= 1'b0;",
                "endmodule",
            ]
        )
        + "\n"
    )
    with pytest.raises(RuntimeError, match="extra ports: clk"):
        _assert_generated_interface_matches(
            rtl_path=rtl_path,
            module_name="TopModule",
            expected_signals=[{"name": "zero", "direction": "OUTPUT", "width": 1}],
        )


def test_bind_benchmark_oracle_assets_repoints_design_context(tmp_path: Path):
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    test_sv.write_text("module tb; endmodule\n")
    ref_sv.write_text("module RefModule; endmodule\n")

    design_context_path = tmp_path / "design_context.json"
    design_context_path.write_text(
        """
{
  "design_context_hash": "abc123",
  "nodes": {
    "TopModule": {
      "rtl_file": "rtl/TopModule.sv",
      "testbench_file": "rtl/TopModule_tb.sv"
    }
  },
  "top_module": "TopModule",
  "execution_policy": {
    "preset": "benchmark"
  }
}
""".strip()
        + "\n"
    )

    bound_node, bound_tb, bound_ref = _bind_benchmark_oracle_assets(
        design_context_path=design_context_path,
        target_module_name="TopModule",
        test_sv=test_sv,
        ref_sv=ref_sv,
    )
    assert bound_node == "TopModule"
    assert bound_tb == str(test_sv.resolve())
    assert bound_ref == str(ref_sv.resolve())

    payload = json.loads(design_context_path.read_text())
    node = payload["nodes"]["TopModule"]
    assert node["testbench_file"] == str(test_sv.resolve())
    assert node["oracle_ref_file"] == str(ref_sv.resolve())
    assert payload["execution_policy"]["disable_tb_generation"] is True
    assert payload["execution_policy"]["debug_rtl_only"] is True
    assert payload["execution_policy"]["benchmark_use_public_testbench"] is True


def test_build_parser_includes_orchestrated_flags():
    parser = build_parser()
    args = parser.parse_args([])
    assert hasattr(args, "legacy_lightweight")
    assert hasattr(args, "pipeline_timeout")
    assert args.legacy_lightweight is False
    assert args.pipeline_timeout == 180.0


def _benchmark_fixture_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "verilog_eval"
    prompts_dir = root / "dataset_spec-to-rtl"
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(parents=True)
    prompts_dir.mkdir(parents=True)
    (scripts_dir / "sv-iv-analyze").write_text("#!/usr/bin/env bash\n")
    (root / "Makefile.in").write_text("all:\n")
    (prompts_dir / "Prob001_demo_prompt.txt").write_text("Module: demo\n")
    (prompts_dir / "Prob001_test.sv").write_text("module tb; endmodule\n")
    (prompts_dir / "Prob001_ref.sv").write_text("module ref; endmodule\n")
    return root, prompts_dir


def test_run_from_args_defaults_to_orchestrated_mode(tmp_path: Path, monkeypatch):
    framework_root, prompts_dir = _benchmark_fixture_tree(tmp_path)
    cfg = load_runtime_config()
    cfg.benchmark.verilog_eval_root = str(framework_root)
    cfg.benchmark.prompts_dir = str(prompts_dir)
    cfg.benchmark.output_root = str(tmp_path / "out")
    cfg.tools.verilator_path = "true"
    cfg.tools.iverilog_path = "true"
    cfg.tools.vvp_path = "true"

    captured = {}

    monkeypatch.setattr("apps.cli.run_verilog_eval.get_runtime_config", lambda: cfg)
    monkeypatch.setattr("apps.cli.run_verilog_eval._has_langchain_schema", lambda: True)
    monkeypatch.setattr("apps.cli.run_verilog_eval.connection_params_from_config", lambda: object())
    monkeypatch.setattr("apps.cli.run_verilog_eval._ensure_broker_connection", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._resolve_tool", lambda configured, default_name: "/bin/true")

    def fake_run_mode(**kwargs):  # noqa: ANN001
        captured["legacy"] = kwargs["legacy_lightweight"]
        out_dir = kwargs["out_dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.txt").write_text("pass_rate = 1.0\n")
        (out_dir / "summary.csv").write_text("Prob001,1,1,1.0,.\n")
        (out_dir / "aggregate.json").write_text("{}\n")

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_mode", fake_run_mode)

    args = argparse.Namespace(
        config="config/runtime.yaml",
        preset="benchmark",
        sampled=False,
        legacy_lightweight=False,
        pipeline_timeout=180.0,
        build_dir=None,
        max_problems=0,
        only_problem=[],
    )
    run_from_args(args)
    assert captured["legacy"] is False


def test_run_from_args_legacy_flag_uses_legacy_mode(tmp_path: Path, monkeypatch):
    framework_root, prompts_dir = _benchmark_fixture_tree(tmp_path)
    cfg = load_runtime_config()
    cfg.benchmark.verilog_eval_root = str(framework_root)
    cfg.benchmark.prompts_dir = str(prompts_dir)
    cfg.benchmark.output_root = str(tmp_path / "out")
    cfg.tools.iverilog_path = "true"
    cfg.tools.vvp_path = "true"

    captured = {}

    monkeypatch.setattr("apps.cli.run_verilog_eval.get_runtime_config", lambda: cfg)
    monkeypatch.setattr("apps.cli.run_verilog_eval._has_langchain_schema", lambda: True)
    monkeypatch.setattr("apps.cli.run_verilog_eval._resolve_tool", lambda configured, default_name: "/bin/true")

    def fake_run_mode(**kwargs):  # noqa: ANN001
        captured["legacy"] = kwargs["legacy_lightweight"]

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_mode", fake_run_mode)

    args = argparse.Namespace(
        config="config/runtime.yaml",
        preset="benchmark",
        sampled=False,
        legacy_lightweight=True,
        pipeline_timeout=180.0,
        build_dir=None,
        max_problems=0,
        only_problem=[],
    )
    run_from_args(args)
    assert captured["legacy"] is True


def test_run_mode_continues_on_orchestrated_failure(tmp_path: Path, monkeypatch):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("prompt\n")
    test_sv.write_text("module tb; endmodule\n")
    ref_sv.write_text("module ref; endmodule\n")
    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)

    monkeypatch.setattr("apps.cli.run_verilog_eval.connection_params_from_config", lambda: object())
    monkeypatch.setattr("apps.cli.run_verilog_eval._ensure_broker_connection", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._purge_benchmark_queues", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval.start_workers", lambda params, stop_event: [])
    monkeypatch.setattr("apps.cli.run_verilog_eval.stop_workers", lambda workers, stop_event: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._isolated_task_memory", lambda path: contextlib.nullcontext())
    monkeypatch.setattr(
        "apps.cli.run_verilog_eval._generate_one_sample_orchestrated",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("orchestrated failure")),
    )
    called = {"sample_test": 0}

    def fake_sample_test(**kwargs):  # noqa: ANN001
        called["sample_test"] += 1

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_sample_test", fake_sample_test)
    monkeypatch.setattr("apps.cli.run_verilog_eval._run_optional_failure_reports", lambda root, build_dir, summary_csv: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._write_internal_summary", lambda **kwargs: None)

    def fake_analyze(root, out_dir):  # noqa: ANN001
        summary_txt = out_dir / "summary.txt"
        summary_csv = out_dir / "summary.csv"
        summary_txt.write_text("pass_rate = 0.0\n")
        summary_csv.write_text("Prob001,0,1,0.0,runner_error\n")
        return summary_txt, summary_csv

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_official_analyze", fake_analyze)

    _run_mode(
        root=tmp_path,
        out_dir=tmp_path / "out",
        cases=[case],
        sample_cfg={"n": 1, "temperature": 0.0, "top_p": 0.01},
        run_label="canonical",
        iverilog_bin="/bin/true",
        vvp_bin="/bin/true",
        legacy_lightweight=False,
        pipeline_timeout_s=5.0,
    )
    assert called["sample_test"] == 1
    sample_dir = tmp_path / "out" / "Prob001"
    assert (sample_dir / "Prob001_sample01.sv").exists()
    assert (sample_dir / "Prob001_sample01-sv-generate.log").exists()
    iv_log = sample_dir / "Prob001_sample01-sv-iv-test.log"
    assert iv_log.exists()
    assert "RUNNER_ERROR stage=generation" in iv_log.read_text()
    assert "orchestrated failure" in iv_log.read_text()


def test_run_mode_continues_when_orchestrator_reports_failed_node(tmp_path: Path, monkeypatch):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("prompt\n")
    test_sv.write_text("module tb; endmodule\n")
    ref_sv.write_text("module RefModule(output zero); endmodule\n")
    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)

    monkeypatch.setattr("apps.cli.run_verilog_eval.connection_params_from_config", lambda: object())
    monkeypatch.setattr("apps.cli.run_verilog_eval._ensure_broker_connection", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._purge_benchmark_queues", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval.start_workers", lambda params, stop_event: [])
    monkeypatch.setattr("apps.cli.run_verilog_eval.stop_workers", lambda workers, stop_event: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._isolated_task_memory", lambda path: contextlib.nullcontext())

    def fake_generate(**kwargs):  # noqa: ANN001
        sample_dir = kwargs["sample_dir"]
        sample_dir.mkdir(parents=True, exist_ok=True)
        name = f"{kwargs['case'].problem_id}_sample{kwargs['sample_index']:02d}"
        (sample_dir / f"{name}.sv").write_text("module TopModule(output zero); assign zero = 1'b0; endmodule\n")
        raise RuntimeError("Pipeline did not complete successfully for all nodes: TopModule=FAILED")

    monkeypatch.setattr("apps.cli.run_verilog_eval._generate_one_sample_orchestrated", fake_generate)
    called = {"sample_test": 0}

    def fake_sample_test(**kwargs):  # noqa: ANN001
        called["sample_test"] += 1

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_sample_test", fake_sample_test)
    monkeypatch.setattr("apps.cli.run_verilog_eval._run_optional_failure_reports", lambda root, build_dir, summary_csv: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._write_internal_summary", lambda **kwargs: None)

    def fake_analyze(root, out_dir):  # noqa: ANN001
        summary_txt = out_dir / "summary.txt"
        summary_csv = out_dir / "summary.csv"
        summary_txt.write_text("pass_rate = 0.0\n")
        summary_csv.write_text("Prob001,0,1,0.0,pipeline_failed\n")
        return summary_txt, summary_csv

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_official_analyze", fake_analyze)

    _run_mode(
        root=tmp_path,
        out_dir=tmp_path / "out",
        cases=[case],
        sample_cfg={"n": 1, "temperature": 0.0, "top_p": 0.01},
        run_label="canonical",
        iverilog_bin="/bin/true",
        vvp_bin="/bin/true",
        legacy_lightweight=False,
        pipeline_timeout_s=5.0,
    )
    assert called["sample_test"] == 1
    iv_log = tmp_path / "out" / "Prob001" / "Prob001_sample01-sv-iv-test.log"
    assert iv_log.exists()
    assert "RUNNER_ERROR stage=generation" in iv_log.read_text()
    assert "TopModule=FAILED" in iv_log.read_text()


def test_run_mode_orchestrated_uses_public_tb_execution_policy(tmp_path: Path, monkeypatch):
    prompt_path = tmp_path / "Prob001_prompt.txt"
    test_sv = tmp_path / "Prob001_test.sv"
    ref_sv = tmp_path / "Prob001_ref.sv"
    prompt_path.write_text("prompt\n")
    test_sv.write_text("module tb; endmodule\n")
    ref_sv.write_text("module ref; endmodule\n")
    case = PromptCase(problem_id="Prob001", prompt_path=prompt_path, test_sv=test_sv, ref_sv=ref_sv)

    monkeypatch.setattr("apps.cli.run_verilog_eval.connection_params_from_config", lambda: object())
    monkeypatch.setattr("apps.cli.run_verilog_eval._ensure_broker_connection", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._purge_benchmark_queues", lambda params: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval.start_workers", lambda params, stop_event: [])
    monkeypatch.setattr("apps.cli.run_verilog_eval.stop_workers", lambda workers, stop_event: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._isolated_task_memory", lambda path: contextlib.nullcontext())

    captured = {}

    def fake_generate(**kwargs):  # noqa: ANN001
        captured["execution_policy"] = kwargs["execution_policy"]
        sample_dir = kwargs["sample_dir"]
        sample_dir.mkdir(parents=True, exist_ok=True)
        name = f"{kwargs['case'].problem_id}_sample{kwargs['sample_index']:02d}"
        (sample_dir / f"{name}.sv").write_text("module TopModule; endmodule\n")
        (sample_dir / f"{name}-sv-generate.log").write_text("status = SUCCESS\n")

    monkeypatch.setattr("apps.cli.run_verilog_eval._generate_one_sample_orchestrated", fake_generate)
    monkeypatch.setattr("apps.cli.run_verilog_eval._run_sample_test", lambda **kwargs: None)

    def fake_analyze(root, out_dir):  # noqa: ANN001
        summary_txt = out_dir / "summary.txt"
        summary_csv = out_dir / "summary.csv"
        summary_txt.write_text("pass_rate = 1.0\n")
        summary_csv.write_text("Prob001,1,1,1.0,.\n")
        return summary_txt, summary_csv

    monkeypatch.setattr("apps.cli.run_verilog_eval._run_official_analyze", fake_analyze)
    monkeypatch.setattr("apps.cli.run_verilog_eval._run_optional_failure_reports", lambda root, build_dir, summary_csv: None)
    monkeypatch.setattr("apps.cli.run_verilog_eval._write_internal_summary", lambda **kwargs: None)

    _run_mode(
        root=tmp_path,
        out_dir=tmp_path / "out",
        cases=[case],
        sample_cfg={"n": 1, "temperature": 0.0, "top_p": 0.01},
        run_label="canonical",
        iverilog_bin="/bin/true",
        vvp_bin="/bin/true",
        legacy_lightweight=False,
        pipeline_timeout_s=5.0,
    )

    policy = captured["execution_policy"]
    assert policy["benchmark_mode"] is True
    assert policy["benchmark_use_public_testbench"] is True
    assert policy["disable_tb_generation"] is True
    assert policy["debug_rtl_only"] is True


def test_write_generate_log_uses_resp_tokens_key(tmp_path: Path):
    log_path = tmp_path / "sample.log"
    _write_generate_log(
        path=log_path,
        status="SUCCESS",
        prompt_tokens=123,
        resp_tokens=45,
        cost_usd=0.123456,
        details="ok",
    )
    text = log_path.read_text()
    assert "prompt_tokens = 123" in text
    assert "resp_tokens = 45" in text
    assert "response_tokens" not in text


def test_isolated_task_memory_falls_back_when_default_backup_is_not_removable(tmp_path: Path, monkeypatch):
    task_memory_root = tmp_path / "task_memory"
    default_backup = tmp_path / "task_memory.benchmark_backup"
    task_memory_root.mkdir()
    default_backup.mkdir()
    (task_memory_root / "original.txt").write_text("keep\n", encoding="utf-8")
    (default_backup / "foreign.txt").write_text("preserve\n", encoding="utf-8")

    original_rmtree = run_verilog_eval.shutil.rmtree

    def fake_rmtree(path, ignore_errors=False):  # noqa: ANN001
        if Path(path) == default_backup and not ignore_errors:
            raise PermissionError("simulated permission denied")
        return original_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(run_verilog_eval.shutil, "rmtree", fake_rmtree)

    with _isolated_task_memory(task_memory_root):
        assert task_memory_root.exists()
        assert not (task_memory_root / "original.txt").exists()
        (task_memory_root / "ephemeral.txt").write_text("temp\n", encoding="utf-8")

    assert (task_memory_root / "original.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (task_memory_root / "ephemeral.txt").exists()
    assert (default_backup / "foreign.txt").read_text(encoding="utf-8") == "preserve\n"
