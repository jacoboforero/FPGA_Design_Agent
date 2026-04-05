from orchestrator.orchestrator_service import (
    _extract_benchmark_mismatch_count,
    _finalizer_active,
    _is_near_miss_sim_failure,
)
from core.runtime.config import get_runtime_config, set_runtime_config


def test_extract_benchmark_mismatch_count_returns_last_match():
    log_output = "\n".join(
        [
            "[run]",
            "Mismatches: 3 in 41 samples",
            "[analysis]",
            "Benchmark oracle comparison reported failure (nonzero mismatches=3); treating as failure.",
            "Mismatches: 7 in 41 samples",
        ]
    )

    assert _extract_benchmark_mismatch_count(log_output) == 7


def test_extract_benchmark_mismatch_count_returns_none_without_marker():
    assert _extract_benchmark_mismatch_count("Simulation failed with assertion") is None


def test_is_near_miss_sim_failure_true_within_threshold():
    log_output = "Mismatches: 12 in 41 samples"
    assert _is_near_miss_sim_failure(log_output, max_mismatches=20) is True


def test_is_near_miss_sim_failure_false_for_timeout():
    log_output = "TIMEOUT\nMismatches: 4 in 41 samples"
    assert _is_near_miss_sim_failure(log_output, max_mismatches=20) is False


def test_is_near_miss_sim_failure_false_when_outside_threshold():
    assert _is_near_miss_sim_failure("Mismatches: 0 in 41 samples", max_mismatches=20) is False
    assert _is_near_miss_sim_failure("Mismatches: 33 in 41 samples", max_mismatches=20) is False


def test_finalizer_active_requires_both_flag_and_workers():
    original = get_runtime_config().model_copy(deep=True)
    cfg = original.model_copy(deep=True)
    cfg.rag.finalizer.enabled = False
    cfg.workers.pool_sizes.finalizer = 1
    set_runtime_config(cfg)
    try:
        assert _finalizer_active() is False
        cfg.rag.finalizer.enabled = True
        cfg.workers.pool_sizes.finalizer = 0
        set_runtime_config(cfg)
        assert _finalizer_active() is False
        cfg.workers.pool_sizes.finalizer = 1
        set_runtime_config(cfg)
        assert _finalizer_active() is True
    finally:
        set_runtime_config(original)
