from __future__ import annotations

from apps.cli.cli import _apply_runtime_cli_overrides, build_parser
from core.runtime.config import get_runtime_config, set_runtime_config


def test_apply_runtime_cli_overrides_toggles_rag_enabled():
    original = get_runtime_config().model_copy(deep=True)
    cfg = original.model_copy(deep=True)
    cfg.rag.enabled = True
    set_runtime_config(cfg)
    try:
        _apply_runtime_cli_overrides(rag_override="off")
        assert get_runtime_config().rag.enabled is False
        _apply_runtime_cli_overrides(rag_override="on")
        assert get_runtime_config().rag.enabled is True
    finally:
        set_runtime_config(original)


def test_apply_runtime_cli_overrides_enables_deterministic_llm_and_seed():
    original = get_runtime_config().model_copy(deep=True)
    cfg = original.model_copy(deep=True)
    cfg.llm.deterministic = False
    cfg.llm.seed = None
    set_runtime_config(cfg)
    try:
        _apply_runtime_cli_overrides(rag_override=None, llm_deterministic=True, llm_seed=17)
        assert get_runtime_config().llm.deterministic is True
        assert get_runtime_config().llm.seed == 17
    finally:
        set_runtime_config(original)


def test_build_parser_accepts_rag_toggle():
    parser = build_parser()
    args = parser.parse_args(["--rag", "off"])
    assert args.rag == "off"


def test_build_parser_accepts_llm_deterministic_flags():
    parser = build_parser()
    args = parser.parse_args(["--llm-deterministic", "--llm-seed", "11"])
    assert args.llm_deterministic is True
    assert args.llm_seed == 11
