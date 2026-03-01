from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from apps.cli.run_verilog_eval import (
    PromptCase,
    _discover_prompt_cases,
    _ensure_framework,
    _load_oracle_manifest,
    _run_official_analyze,
    _run_sample_test,
    _resolve_target_interface,
    _resolve_target_module_name,
    _summary_metrics,
    _summary_rows,
)


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


def test_discover_prompt_cases_maps_processed_prompts_to_dataset(tmp_path: Path):
    prompts_dir = tmp_path / "processed_prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()

    (prompts_dir / "Prob079_fsm3onehot.txt").write_text("prompt A\n")
    (prompts_dir / "Prob020_mt2015_eq2.txt").write_text("prompt B\n")
    (prompts_dir / "readme.txt").write_text("not a problem prompt\n")

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
    assert cases[0].prompt_path.name == "Prob020_mt2015_eq2.txt"
    assert cases[1].prompt_path.name == "Prob079_fsm3onehot.txt"


def test_discover_prompt_cases_resolves_suffix_dataset_assets(tmp_path: Path):
    prompts_dir = tmp_path / "processed_prompts"
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
    prompts_dir = tmp_path / "processed_prompts"
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
    prompts_dir = tmp_path / "processed_prompts"
    dataset_dir = tmp_path / "dataset_spec-to-rtl"
    prompts_dir.mkdir()
    dataset_dir.mkdir()

    (prompts_dir / "Prob010_demo.txt").write_text("prompt\n")
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
