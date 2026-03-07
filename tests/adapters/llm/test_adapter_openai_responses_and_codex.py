import pytest
from unittest.mock import AsyncMock, MagicMock

from adapters.llm.adapter_openai import OpenAIGateway
from adapters.llm.gateway import Message, MessageRole, GenerationConfig


@pytest.mark.asyncio
async def test_generate_with_responses_api_calls_responses_create(mocker):
    mock_client = AsyncMock()
    mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)

    # Mock a Responses-API style response
    mock_response = MagicMock()
    # Simulate .output structure
    mock_response.output = [{
        "content": [{"type": "output_text", "text": "Hello from Responses API"}]
    }]
    mock_response.model = "gpt-4o"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 5
    mock_response.usage.completion_tokens = 7
    mock_response.usage.total_tokens = 12

    mock_client.responses.create = AsyncMock(return_value=mock_response)

    gateway = OpenAIGateway(api_key="sk-test-key")

    cfg = GenerationConfig(use_responses_api=True)
    messages = [Message(role=MessageRole.USER, content="Say hello")]

    resp = await gateway.generate(messages, cfg)

    # Ensure we called the Responses API
    mock_client.responses.create.assert_called()
    assert "Responses API" in resp.content
    assert resp.provider == "openai"


@pytest.mark.asyncio
async def test_generate_with_codex_uses_completions_api(mocker):
    mock_client = AsyncMock()
    mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)

    # Mock completions-style response for Codex
    mock_choice = MagicMock()
    mock_choice.text = "def add(a, b):\n    return a + b\n"
    mock_choice.finish_reason = "stop"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-5.3-codex"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 30
    mock_response.usage.total_tokens = 40

    mock_client.completions.create = AsyncMock(return_value=mock_response)

    gateway = OpenAIGateway(api_key="sk-test-key", model="gpt-5.3-codex")

    messages = [Message(role=MessageRole.USER, content="Write a Python add function")] 
    resp = await gateway.generate(messages)

    # Called completions.create (Codex path)
    mock_client.completions.create.assert_called()
    assert "def add" in resp.content
    assert resp.model_name == "gpt-5.3-codex"
    assert resp.provider == "openai"
