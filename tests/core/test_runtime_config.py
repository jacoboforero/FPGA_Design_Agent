from __future__ import annotations

from pathlib import Path

from core.runtime.config import load_runtime_config


def test_runtime_config_defaults_load():
    cfg = load_runtime_config()
    assert cfg.active_preset in cfg.presets
    assert cfg.broker.url
    assert cfg.broker.results_consume_mode == "consume"
    assert cfg.cli.execution_narrator_async is True
    assert cfg.cli.execution_narrator_order_mode == "strict"
    assert cfg.cli.execution_narrator_queue_max_events == 256
    assert cfg.workers.pool_sizes.implementation == 2
    assert cfg.workers.pool_sizes.simulation == 2
    assert cfg.llm.rate_control.adaptive_enabled is True
    assert cfg.llm.rate_control.max_in_flight_default == 6
    assert cfg.benchmark.canonical.n == 1
    assert cfg.benchmark.sampled.temperature == 0.8
    assert cfg.benchmark.verilog_eval_root == "third_party/verilog-eval"
    assert cfg.benchmark.prompts_dir == "third_party/verilog-eval/dataset_spec-to-rtl"
    assert cfg.presets["benchmark"].allow_repair_loop is True


def test_runtime_config_preset_override(tmp_path: Path):
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(
        "\n".join(
            [
                "active_preset: engineer_fast",
                "presets:",
                "  engineer_fast:",
                "    spec_profile: engineer_fast",
                "    verification_profile: hybrid_scoreboard",
                "  benchmark:",
                "    spec_profile: benchmark",
                "    verification_profile: oracle_compare",
                "    allow_repair_loop: false",
                "    interactive_spec_helper: false",
                "    benchmark_mode: true",
            ]
        )
    )
    cfg = load_runtime_config(config_path, preset_override="benchmark")
    assert cfg.active_preset == "benchmark"
    assert cfg.resolved_preset.spec_profile == "benchmark"
    assert cfg.resolved_preset.allow_repair_loop is False
