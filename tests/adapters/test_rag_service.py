from __future__ import annotations

from adapters.rag.rag_service import archive_final_design, retrieve_for_stage
from core.runtime.config import get_runtime_config, set_runtime_config


def test_retrieve_for_stage_skips_benchmark_when_disabled():
    original = get_runtime_config().model_copy(deep=True)
    cfg = original.model_copy(deep=True)
    cfg.rag.enabled = True
    cfg.rag.allow_benchmark = False
    set_runtime_config(cfg)
    try:
        context, metadata = retrieve_for_stage(
            "implementation",
            "counter with reset",
            execution_policy={"run_kind": "benchmark", "benchmark_flow_mode": "orchestrated"},
        )
        assert context == ""
        assert metadata["used"] is False
        assert metadata["skip_reason"] == "benchmark_disabled"
    finally:
        set_runtime_config(original)


def test_archive_final_design_skips_when_finalizer_disabled():
    original = get_runtime_config().model_copy(deep=True)
    cfg = original.model_copy(deep=True)
    cfg.rag.enabled = True
    cfg.rag.finalizer.enabled = False
    set_runtime_config(cfg)
    try:
        metadata = archive_final_design(
            stage="finalizer",
            record={"module_name": "buf1_leaf", "rtl": "module buf1_leaf; endmodule\n"},
            execution_policy={"run_kind": "engineer"},
        )
        assert metadata["used"] is False
        assert metadata["skip_reason"] == "stage_disabled"
    finally:
        set_runtime_config(original)
