from __future__ import annotations

from pathlib import Path

from core.runtime.config import load_runtime_config


def test_runtime_config_defaults_load():
    cfg = load_runtime_config()
    assert cfg.run.spec_profile.interaction == "interactive"
    assert cfg.run.spec_profile.rigor_level == "L3"
    assert cfg.run.verification_profile == "testbench-agent"
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
    assert cfg.benchmark.flow_mode == "direct_single_module"
    assert cfg.benchmark.prompt_mode == "raw_verilog_eval"
    assert cfg.benchmark.use_public_testbench is True
    assert cfg.benchmark.interface_equivalence == "canonical_width"
    assert cfg.benchmark.rtl_language == "systemverilog"
    assert cfg.rag.enabled is True
    assert cfg.rag.embedding_provider == "openai"
    assert cfg.rag.openai_embedding_model == "text-embedding-3-small"
    assert cfg.rag.allow_benchmark is False
    assert cfg.rag.finalizer.enabled is False
    assert cfg.workers.pool_sizes.finalizer == 0


def test_runtime_config_manifest_include_merge(tmp_path: Path):
    (tmp_path / "run.yaml").write_text(
        "\n".join(
            [
                "run:",
                "  spec_profile:",
                "    interaction: non_interactive",
                "    rigor_level: L0",
                "  verification_profile: verilog-eval",
            ]
        )
    )
    (tmp_path / "infra.yaml").write_text(
        "\n".join(
            [
                "infrastructure:",
                "  broker:",
                "    url: amqp://example/",
                "  tool_paths:",
                "    verilator: /usr/local/bin/verilator",
            ]
        )
    )
    (tmp_path / "runtime.yaml").write_text("includes:\n  - run.yaml\n  - infra.yaml\n")

    cfg = load_runtime_config(tmp_path / "runtime.yaml")
    assert cfg.run.spec_profile.interaction == "non_interactive"
    assert cfg.run.spec_profile.rigor_level == "L0"
    assert cfg.run.verification_profile == "verilog-eval"
    assert cfg.broker.url == "amqp://example/"
    assert cfg.tools.verilator_path == "/usr/local/bin/verilator"


def test_runtime_config_rag_manifest_merge(tmp_path: Path):
    (tmp_path / "rag.yaml").write_text(
        "\n".join(
            [
                "rag:",
                "  enabled: true",
                "  fail_open: false",
                "  embedding_provider: openai",
                "  openai_embedding_model: text-embedding-3-small",
                "  implementation:",
                "    top_k: 5",
                "  debug:",
                "    max_context_chars: 2222",
            ]
        )
    )
    (tmp_path / "runtime.yaml").write_text("includes:\n  - rag.yaml\n")

    cfg = load_runtime_config(tmp_path / "runtime.yaml")
    assert cfg.rag.enabled is True
    assert cfg.rag.fail_open is False
    assert cfg.rag.implementation.top_k == 5
    assert cfg.rag.debug.max_context_chars == 2222


def test_runtime_benchmark_manifest_disables_rag_by_default():
    cfg = load_runtime_config(Path("config/runtime.benchmark.yaml"))
    assert cfg.run.verification_profile == "verilog-eval"
    assert cfg.rag.enabled is False
    assert cfg.rag.allow_benchmark is False
