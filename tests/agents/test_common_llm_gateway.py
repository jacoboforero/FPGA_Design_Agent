import pytest

from agents.common import llm_gateway as common_gateway


def test_init_llm_gateway_delegates_and_respects_agent_override(monkeypatch):
    """agents.common.llm_gateway.init_llm_gateway should delegate to adapter factory
    and honor per-agent environment overrides (prefix-style only)."""
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    # Default (no agent_type) -> openai
    gw_default = common_gateway.init_llm_gateway()
    assert gw_default is not None
    assert gw_default.provider == "openai"

    # Override for debug -> anthropic (prefix-style)
    monkeypatch.setenv("DEBUG_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anth-key")

    gw_debug = common_gateway.init_llm_gateway("debug")
    assert gw_debug is not None
    assert gw_debug.provider == "anthropic"


def test_worker_initializes_with_agent_specific_gateway(monkeypatch):
    """Agent worker constructors should receive the agent-specific gateway."""
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    # Spec helper override -> groq (prefix-style)
    monkeypatch.setenv("SPEC_HELPER_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    from agents.spec_helper.worker import SpecHelperWorker

    worker = SpecHelperWorker(connection_params=None, stop_event=None)
    assert worker.gateway is not None
    assert worker.gateway.provider == "groq"
