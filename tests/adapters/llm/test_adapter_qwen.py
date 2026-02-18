"""
Unit tests for adapters/llm/adapter_qwen.py

Renamed from the previous test file for the qwen3:4b adapter.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from adapters.llm.adapter_qwen import QwenLocalGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# The remainder of the tests mirror the original test_adapter_qwen34b


class TestQwenLocalGatewayInit:
    def test_init_with_defaults(self):
        gateway = QwenLocalGateway()
        assert gateway._model == "qwen3:4b"
        assert gateway._base_url == "http://localhost:11434"
        assert gateway._timeout == 300.0

    def test_init_with_custom_base_url(self):
        gateway = QwenLocalGateway(ollama_base_url="http://192.168.1.100:11434")
        assert gateway._base_url == "http://192.168.1.100:11434"

    def test_init_strips_trailing_slash(self):
        gateway = QwenLocalGateway(ollama_base_url="http://localhost:11434/")
        assert gateway._base_url == "http://localhost:11434"

    def test_init_with_custom_timeout(self):
        gateway = QwenLocalGateway(timeout=600.0)
        assert gateway._timeout == 600.0

    def test_init_constructs_api_url(self):
        gateway = QwenLocalGateway()
        assert gateway._api_url == "http://localhost:11434/api/chat"


class TestQwenLocalGatewayProperties:
    def test_model_name_property(self):
        gateway = QwenLocalGateway()
        assert gateway.model_name == "qwen3:4b"

    def test_provider_property(self):
        gateway = QwenLocalGateway()
        assert gateway.provider == "qwen-local"

    def test_supports_files(self):
        gateway = QwenLocalGateway()
        assert gateway.supports_files is True


class TestQwenMessageConversion:
    def test_convert_simple_user_message(self):
        gateway = QwenLocalGateway()
        message = Message(role=MessageRole.USER, content="Hello")
        converted = gateway._convert_messages([message])
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"

    def test_convert_system_message(self):
        gateway = QwenLocalGateway()
        message = Message(role=MessageRole.SYSTEM, content="You are helpful")
        converted = gateway._convert_messages([message])
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are helpful"

    def test_convert_multi_turn(self):
        gateway = QwenLocalGateway()
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="I need coding help"),
        ]
        converted = gateway._convert_messages(messages)
        assert len(converted) == 3
        assert converted[0]["role"] == "user"


class TestQwenConfigValidation:
    def test_validate_temperature_in_range(self):
        gateway = QwenLocalGateway()
        for temp in [0.0, 0.5, 1.0, 2.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp

    def test_validate_top_p_in_range(self):
        gateway = QwenLocalGateway()
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9

    def test_validate_top_k_supported(self):
        gateway = QwenLocalGateway()
        config = GenerationConfig(top_k=40)
        validated = gateway.validate_config(config)
        assert validated.top_k == 40


class TestQwenResponseConversion:
    def test_convert_successful_response(self):
        gateway = QwenLocalGateway()
        ollama_response = {
            "model": "qwen3:4b",
            "created_at": "2025-02-08T00:00:00.000000Z",
            "message": {"role": "assistant", "content": "Here's a Verilog module..."},
            "done": True,
            "total_duration": 5000000000,
            "load_duration": 500000000,
            "prompt_eval_count": 50,
            "prompt_eval_duration": 100000000,
            "eval_count": 100,
            "eval_duration": 4500000000,
        }
        converted = gateway._convert_response(ollama_response)
        assert isinstance(converted, ModelResponse)
        assert converted.content == "Here's a Verilog module..."
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100
        assert converted.provider == "qwen-local"

    def test_convert_response_with_content(self):
        gateway = QwenLocalGateway()
        ollama_response = {"model": "qwen3:4b", "message": {"role": "assistant", "content": "Generated code"}, "done": True, "prompt_eval_count": 50, "eval_count": 100}
        converted = gateway._convert_response(ollama_response)
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100


class TestQwenGenerate:
    @pytest.mark.asyncio
    async def test_generate_with_config(self):
        gateway = QwenLocalGateway()
        with patch("adapters.llm.adapter_qwen.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={"model": "qwen3:4b", "message": {"role": "assistant", "content": "Generated code"}, "done": True, "prompt_eval_count": 50, "eval_count": 100})
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            messages = [Message(role=MessageRole.USER, content="test")]
            config = GenerationConfig(temperature=0.8)

            result = await gateway.generate(messages, config)
            assert isinstance(result, ModelResponse)
            assert result.content == "Generated code"

    @pytest.mark.asyncio
    async def test_generate_handles_timeout(self):
        gateway = QwenLocalGateway(timeout=1.0)
        with patch("adapters.llm.adapter_qwen.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Request timed out"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            messages = [Message(role=MessageRole.USER, content="test")]
            with pytest.raises(RuntimeError, match="timed out"):
                await gateway.generate(messages)

    @pytest.mark.asyncio
    async def test_generate_handles_http_errors(self):
        gateway = QwenLocalGateway()
        with patch("adapters.llm.adapter_qwen.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock(side_effect=Exception("404 Not Found"))
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            messages = [Message(role=MessageRole.USER, content="test")]
            with pytest.raises(RuntimeError):
                await gateway.generate(messages)


class TestQwenErrorHandling:
    def test_custom_ollama_url(self):
        gateway = QwenLocalGateway(ollama_base_url="http://ollama.example.com:11434")
        assert gateway._api_url == "http://ollama.example.com:11434/api/chat"

    @pytest.mark.asyncio
    async def test_generate_with_provider_specific_options(self):
        gateway = QwenLocalGateway()
        with patch("adapters.llm.adapter_qwen.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={"model": "qwen3:4b", "message": {"role": "assistant", "content": "result"}, "done": True, "prompt_eval_count": 10, "eval_count": 20})
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            messages = [Message(role=MessageRole.USER, content="test")]
            config = GenerationConfig(temperature=0.7, provider_specific={"num_keep": 5, "penalize_newline": True})
            result = await gateway.generate(messages, config)
            assert mock_client.post.called

    @pytest.mark.asyncio
    async def test_generate_with_functions_option(self):
        gateway = QwenLocalGateway()
        with patch("adapters.llm.adapter_qwen.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={"model": "qwen3:4b", "message": {"role": "assistant", "content": "result"}, "done": True, "prompt_eval_count": 10, "eval_count": 20})
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            messages = [Message(role=MessageRole.USER, content="test")]
            cfg = GenerationConfig(functions=[{"name": "f", "parameters": {"type": "object"}}])

            result = await gateway.generate(messages, cfg)
            assert mock_client.post.called
            payload = mock_client.post.call_args[1]["json"]
            assert "options" in payload
            assert payload["options"].get("functions") == cfg.functions


class TestQwenIntegration:
    def test_api_url_construction(self):
        test_cases = [
            ("http://localhost:11434", "http://localhost:11434/api/chat"),
            ("http://localhost:11434/", "http://localhost:11434/api/chat"),
            ("http://192.168.1.1:11434", "http://192.168.1.1:11434/api/chat"),
            ("https://ollama.example.com", "https://ollama.example.com/api/chat"),
        ]
        for base_url, expected_api_url in test_cases:
            gateway = QwenLocalGateway(ollama_base_url=base_url)
            assert gateway._api_url == expected_api_url
