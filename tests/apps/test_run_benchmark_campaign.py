from __future__ import annotations

from pathlib import Path

import pytest

import scripts.run_benchmark_campaign as campaign


def test_load_campaign_requires_runs(tmp_path: Path):
    cfg = tmp_path / "campaign.yaml"
    cfg.write_text("campaign: demo\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="runs"):
        campaign._load_campaign(cfg)


def test_build_run_command_includes_core_flags():
    cmd, run_root = campaign._build_run_command(
        python_bin="python3",
        campaign_name="demo_campaign",
        campaign_output_root="artifacts/benchmarks/verilog_eval",
        run_item={
            "label": "gpt41",
            "config": "config/runtime.yaml",
            "preset": "benchmark",
            "sampled": True,
            "max_problems": 10,
            "only_problem": ["Prob079"],
            "pipeline_timeout": 90,
        },
    )
    cmd_text = " ".join(cmd)
    assert "apps/cli/cli.py benchmark run" in cmd_text
    assert "--campaign demo_campaign" in cmd_text
    assert "--run-id gpt41" in cmd_text
    assert "--sampled" in cmd_text
    assert "--max-problems 10" in cmd_text
    assert "--only-problem Prob079" in cmd_text
    assert "--pipeline-timeout 90.0" in cmd_text
    assert str(run_root).endswith("artifacts/benchmarks/verilog_eval/demo_campaign/gpt41")
