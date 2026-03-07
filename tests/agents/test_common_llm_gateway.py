import pytest

from agents.common import llm_gateway as common_gateway
from core.runtime.config import LlmAgentOverrideConfig, load_runtime_config, set_runtime_config


@pytest.fixture(autouse=True)
def _reset_runtime_config():
    set_runtime_config(load_runtime_config())
    yield
    set_runtime_config(load_runtime_config())


def test_init_llm_gateway_delegates_and_respects_agent_override(monkeypatch):
    """agents.common.llm_gateway.init_llm_gateway should honor YAML agent overrides."""
    cfg = load_runtime_config()
    cfg.llm.enabled = True
    cfg.llm.provider = "openai"
    cfg.llm.default_model = "gpt-4.1-mini"
    cfg.llm.agent_overrides = {
        "debug": LlmAgentOverrideConfig(provider="groq", model="llama-3.1-8b-instant")
    }
    set_runtime_config(cfg)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    # Default (no agent_type) -> openai
    gw_default = common_gateway.init_llm_gateway()
    assert gw_default is not None
    assert gw_default.provider == "openai"

    # YAML override for debug -> groq
    gw_debug = common_gateway.init_llm_gateway("debug")
    assert gw_debug is not None
    assert gw_debug.provider == "groq"


def test_worker_initializes_with_agent_specific_gateway(monkeypatch):
    """Agent worker constructors should receive the agent-specific gateway."""
    cfg = load_runtime_config()
    cfg.llm.enabled = True
    cfg.llm.provider = "openai"
    cfg.llm.default_model = "gpt-4.1-mini"
    cfg.llm.agent_overrides = {
        "spec_helper": LlmAgentOverrideConfig(provider="groq", model="llama-3.1-8b-instant")
    }
    set_runtime_config(cfg)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    from agents.spec_helper.worker import SpecHelperWorker

    worker = SpecHelperWorker(connection_params=None, stop_event=None)
    assert worker.gateway is not None
    assert worker.gateway.provider == "groq"
