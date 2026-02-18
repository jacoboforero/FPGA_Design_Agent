"""
Shared pytest fixtures for LLM adapter testing.

Provides:
- Fixture factories for test data (messages, configs, responses)
- Mock LLM clients with controllable behavior
- Mocked OpenAI async client
- Standard test response payloads
"""

import pytest
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, Mock

from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# Message Fixtures
# ============================================================================

@pytest.fixture
def sample_user_message() -> Message:
    """A simple user message."""
    return Message(
        role=MessageRole.USER,
        content="Generate a simple Verilog counter module."
    )


@pytest.fixture
def sample_system_message() -> Message:
    """A system message defining behavior."""
    return Message(
        role=MessageRole.SYSTEM,
        content="You are a Verilog code generator. Provide clean, well-commented code."
    )


@pytest.fixture
def sample_assistant_message() -> Message:
    """An assistant response message."""
    return Message(
        role=MessageRole.ASSISTANT,
        content="```verilog\nmodule counter(...);\nendmodule\n```"
    )


@pytest.fixture
def sample_conversation(
    sample_system_message,
    sample_user_message,
    sample_assistant_message
) -> List[Message]:
    """A multi-turn conversation."""
    return [
        sample_system_message,
        sample_user_message,
        sample_assistant_message,
        Message(role=MessageRole.USER, content="Add reset functionality."),
    ]


@pytest.fixture
def message_with_attachments() -> Message:
    """A message with file attachments."""
    return Message(
        role=MessageRole.USER,
        content="Analyze this code:",
        attachments=[
            {"filename": "counter.v", "content": "module counter(...);\nendmodule"},
            {"filename": "spec.md", "content": "# Counter Spec\n- 8-bit counter\n- Active-low reset"},
        ]
    )


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def base_generation_config() -> GenerationConfig:
    """A basic generation config."""
    return GenerationConfig(
        max_tokens=500,
        temperature=0.7,
    )


@pytest.fixture
def minimal_generation_config() -> GenerationConfig:
    """Minimal config (all defaults)."""
    return GenerationConfig()


@pytest.fixture
def custom_generation_config() -> GenerationConfig:
    """Config with all parameters set."""
    return GenerationConfig(
        max_tokens=1000,
        temperature=0.5,
        top_p=0.9,
        top_k=40,
        stop_sequences=["```", "END"],
        provider_specific={"logprobs": 10, "top_logprobs": 3},
    )


# ============================================================================
# Response Fixtures
# ============================================================================

@pytest.fixture
def mock_model_response() -> ModelResponse:
    """A realistic mock LLM response."""
    return ModelResponse(
        content="```verilog\nmodule counter #(parameter WIDTH=8) (\n  input clk,\n  input rst_n,\n  output [WIDTH-1:0] count\n);\n  // counter implementation\nendmodule\n```",
        input_tokens=42,
        output_tokens=128,
        total_tokens=170,
        estimated_cost_usd=0.00342,
        model_name="gpt-4o",
        provider="openai",
        finish_reason="stop",
        raw_response={
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "..."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 42,
                "completion_tokens": 128,
                "total_tokens": 170,
            },
        },
    )


@pytest.fixture
def mock_short_response() -> ModelResponse:
    """A short response (e.g., timeout or brief answer)."""
    return ModelResponse(
        content="module simple();\nendmodule",
        input_tokens=10,
        output_tokens=8,
        total_tokens=18,
        estimated_cost_usd=0.00009,
        model_name="gpt-4o",
        provider="openai",
        finish_reason="stop",
    )


@pytest.fixture
def mock_error_response_data() -> Dict[str, Any]:
    """Raw API error response (for mocking failed requests)."""
    return {
        "error": {
            "type": "rate_limit_error",
            "message": "Rate limit exceeded. Please retry after 30 seconds.",
        }
    }


@pytest.fixture
def mock_openai_response_data() -> Dict[str, Any]:
    """Raw OpenAI API response (for mocking httpx/AsyncOpenAI)."""
    return {
        "id": "chatcmpl-8xxxx",
        "object": "chat.completion",
        "created": 1704067200,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "```verilog\nmodule adder(input [7:0] a, b, output [8:0] sum);\n  assign sum = a + b;\nendmodule\n```",
                },
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 80,
            "total_tokens": 130,
        },
        "system_fingerprint": "fp_xyz",
    }


# ============================================================================
# Mock Client Factories
# ============================================================================

@pytest.fixture
def mock_openai_client(mock_openai_response_data) -> AsyncMock:
    """
    Mock AsyncOpenAI client.
    
    Usage:
        mock_client = mock_openai_client
        mock_client.chat.completions.create.return_value = parsed_response
    """
    client = AsyncMock()
    
    # Setup the response chain: client.chat.completions.create(...)
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = mock_openai_response_data["choices"][0]["message"]["content"]
    mock_completion.choices[0].finish_reason = "stop"
    mock_completion.model = "gpt-4o"
    mock_completion.usage.prompt_tokens = mock_openai_response_data["usage"]["prompt_tokens"]
    mock_completion.usage.completion_tokens = mock_openai_response_data["usage"]["completion_tokens"]
    mock_completion.usage.total_tokens = mock_openai_response_data["usage"]["total_tokens"]
    
    # Make create() return this mock
    client.chat.completions.create = AsyncMock(return_value=mock_completion)
    client.close = AsyncMock()
    
    return client


@pytest.fixture
def mock_transient_error():
    """An error that should trigger retries (network issue)."""
    from openai import APIConnectionError
    return APIConnectionError("Connection failed: temporarily unable to connect")


@pytest.fixture
def mock_auth_error():
    """An error indicating bad credentials."""
    from openai import AuthenticationError
    return AuthenticationError("Invalid API key provided")


@pytest.fixture
def mock_rate_limit_error():
    """An error indicating rate limit."""
    from openai import RateLimitError
    return RateLimitError("Rate limit exceeded")


@pytest.fixture
def mock_invalid_request_error():
    """An error indicating invalid request (should not retry)."""
    from openai import BadRequestError
    return BadRequestError("Invalid request: temperature out of range")


# ============================================================================
# Environment and Config Fixtures
# ============================================================================

@pytest.fixture
def valid_gateway_env(monkeypatch):
    """Set up valid environment for gateway initialization."""
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")


@pytest.fixture
def disabled_llm_env(monkeypatch):
    """Environment with LLMs disabled."""
    monkeypatch.setenv("USE_LLM", "0")


@pytest.fixture
def legacy_openai_env(monkeypatch):
    """Environment for legacy OpenAI mode."""
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")


@pytest.fixture
def config_with_tier_override(monkeypatch):
    """Environment with tier override (legacy mode only)."""
    monkeypatch.setenv("USE_LLM", "1")
    monkeypatch.setenv("GATEWAY_TIER", "budget")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")


@pytest.fixture
def missing_api_keys_env(monkeypatch):
    """Environment with LLM enabled but no API keys."""
    monkeypatch.setenv("USE_LLM", "1")
    # Clear API keys
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


# ============================================================================
# Parametrization Helpers
# ============================================================================

@pytest.fixture(params=[0.0, 0.5, 1.0, 2.0])
def temperature_value(request):
    """Parametrized temperature values for testing constraints."""
    return request.param


@pytest.fixture(params=[0.0, 0.5, 0.9, 1.0])
def top_p_value(request):
    """Parametrized top_p values."""
    return request.param


@pytest.fixture(params=[1, 10, 100, 1000, 2000])
def token_count(request):
    """Parametrized token counts."""
    return request.param


# ============================================================================
# Helper Functions
# ============================================================================

def create_mock_response(
    content: str = "Test response",
    input_tokens: int = 10,
    output_tokens: int = 20,
    model_name: str = "gpt-4o",
    provider: str = "openai",
    finish_reason: str = "stop",
    cost: Optional[float] = None,
) -> ModelResponse:
    """Factory function to quickly create mock responses."""
    return ModelResponse(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=cost or 0.0,
        model_name=model_name,
        provider=provider,
        finish_reason=finish_reason,
    )


def create_mock_message(
    role: MessageRole = MessageRole.USER,
    content: str = "Test message",
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Message:
    """Factory function to quickly create mock messages."""
    return Message(
        role=role,
        content=content,
        attachments=attachments or [],
    )
