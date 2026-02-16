"""
Shared fixtures for LLM adapter integration tests.

Provides realistic test data and helper functions for testing
the interaction between gateway, config, and adapter components.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from adapters.llm.gateway import Message, MessageRole, ModelResponse


@pytest.fixture
def mock_openai_response():
    """Create a realistic OpenAI API response mock."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Generated response"
    mock_response.choices[0].finish_reason = "stop"
    mock_response.model = "gpt-4o"
    mock_response.usage.prompt_tokens = 50
    mock_response.usage.completion_tokens = 75
    mock_response.usage.total_tokens = 125
    del mock_response.model_dump
    return mock_response


@pytest.fixture
def mock_anthropic_response():
    """Create a realistic Anthropic API response mock."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = "Generated response"
    mock_response.stop_reason = "end_turn"
    mock_response.model = "claude-3-opus-20240229"
    mock_response.usage.input_tokens = 50
    mock_response.usage.output_tokens = 75
    mock_response.model_dump = MagicMock(return_value={})
    return mock_response


@pytest.fixture
def mock_groq_response():
    """Create a realistic Groq API response mock."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Generated response"
    mock_response.choices[0].finish_reason = "stop"
    mock_response.model = "llama-3.1-8b-instant"
    mock_response.usage.prompt_tokens = 50
    mock_response.usage.completion_tokens = 75
    mock_response.usage.total_tokens = 125
    del mock_response.model_dump
    return mock_response


@pytest.fixture
def mock_cohere_response():
    """Create a realistic Cohere API response mock."""
    mock_billed_units = MagicMock()
    mock_billed_units.input_tokens = 50
    mock_billed_units.output_tokens = 75
    
    mock_meta = MagicMock()
    mock_meta.billed_units = mock_billed_units
    
    mock_response = MagicMock()
    mock_response.text = "Generated response"
    mock_response.generation_id = "gen-123"
    mock_response.finish_reason = "COMPLETE"
    mock_response.meta = mock_meta
    return mock_response


@pytest.fixture
def message_simple():
    """Simple user message."""
    return [Message(role=MessageRole.USER, content="Hello, can you help?")]


@pytest.fixture
def message_with_system():
    """Messages with system prompt."""
    return [
        Message(role=MessageRole.SYSTEM, content="You are a helpful Verilog expert"),
        Message(role=MessageRole.USER, content="Generate a counter module"),
    ]


@pytest.fixture
def message_multi_turn():
    """Multi-turn conversation."""
    return [
        Message(role=MessageRole.USER, content="Design a counter"),
        Message(role=MessageRole.ASSISTANT, content="Here's a simple counter:\n```verilog\nmodule counter(...)\n```"),
        Message(role=MessageRole.USER, content="Add reset signal"),
    ]


@pytest.fixture
def clean_env(monkeypatch):
    """Clean LLM-related environment variables before test."""
    llm_vars = [
        "LLM_PROVIDER", "LLM_MODEL", "USE_LLM",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY",
        "COHERE_API_KEY", "GOOGLE_API_KEY",
        "PLANNER_LLM_PROVIDER", "IMPLEMENTATION_LLM_PROVIDER",
        "PLANNER_LLM_MODEL", "IMPLEMENTATION_LLM_MODEL",
    ]
    for var in llm_vars:
        monkeypatch.delenv(var, raising=False)
    yield
    # Cleanup after test
    for var in llm_vars:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def with_openai_env(clean_env, monkeypatch):
    """Set up minimal OpenAI environment."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")
    return monkeypatch


@pytest.fixture
def with_anthropic_env(clean_env, monkeypatch):
    """Set up minimal Anthropic environment."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-3-opus-20240229")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    return monkeypatch


@pytest.fixture
def with_groq_env(clean_env, monkeypatch):
    """Set up minimal Groq environment."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
    return monkeypatch


# `with_config_mode_env` fixture removed — centralized gateway_config no longer supported.


@pytest.fixture
def with_cohere_env(clean_env, monkeypatch):
    """Set up minimal Cohere environment."""
    monkeypatch.setenv("LLM_PROVIDER", "cohere")
    monkeypatch.setenv("LLM_MODEL", "command-r-plus")
    monkeypatch.setenv("COHERE_API_KEY", "cohere-test-key")
    return monkeypatch


@pytest.fixture
def with_google_env(clean_env, monkeypatch):
    """Set up minimal Google environment."""
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("LLM_MODEL", "gemini-1.5-pro")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
    return monkeypatch


@pytest.fixture
def with_per_agent_env(clean_env, monkeypatch):
    """Set up per-agent model overrides (prefix-style)."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("IMPLEMENTATION_LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
    return monkeypatch
