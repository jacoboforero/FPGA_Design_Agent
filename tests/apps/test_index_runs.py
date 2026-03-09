from __future__ import annotations

import json
from pathlib import Path

from scripts.index_runs import build_benchmark_index


def test_build_benchmark_index_reads_nested_aggregate_and_manifest(tmp_path: Path):
    repo_root = tmp_path
    artifacts_root = repo_root / "artifacts"
    mode_dir = artifacts_root / "benchmarks" / "verilog_eval" / "campaign_a" / "run_001" / "canonical"
    mode_dir.mkdir(parents=True)

    (mode_dir / "summary.csv").write_text("Prob001,1,1,1.0,.\n", encoding="utf-8")
    (mode_dir / "summary.txt").write_text("pass_rate = 1.0\n", encoding="utf-8")
    (mode_dir / "aggregate.json").write_text(
        json.dumps(
            {
                "aggregate": {"official_metrics": {"pass_rate": 1.0}, "row_count": 1},
                "per_problem": [{"problem_id": "Prob001", "npass": "1", "nsamples": "1"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (mode_dir.parent / "run_manifest.json").write_text(
        json.dumps(
            {
                "preset": "benchmark",
                "status": "success",
                "runtime": {"llm": {"provider": "openai", "default_model": "gpt-4.1"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Should be ignored because summary artifacts are missing.
    ignored_dir = artifacts_root / "benchmarks" / "verilog_eval" / "campaign_a" / "run_001" / "junk"
    ignored_dir.mkdir(parents=True)
    (ignored_dir / "aggregate.json").write_text("{}\n", encoding="utf-8")

    rows, counts = build_benchmark_index(repo_root, artifacts_root)
    assert len(rows) == 1
    row = rows[0]
    assert row["campaign_dir"] == "campaign_a"
    assert row["run_id"] == "run_001"
    assert row["mode"] == "canonical"
    assert row["model"] == "gpt-4.1"
    assert row["provider"] == "openai"
    assert row["preset"] == "benchmark"
    assert float(row["pass_rate"]) == 1.0
    assert int(row["pass_count"]) == 1
    assert int(row["sample_count"]) == 1
    assert counts[row["campaign"]] == 1
