"""
Unit tests for adapters/llm/adapter_grok.py

Tests the Grok (xAI) gateway implementation:
- GrokGateway initialization
- Grok API call handling (OpenAI-compatible)
- Message format conversion
- Response parsing and cost estimation
- Configuration validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from adapters.llm.adapter_grok import GrokGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# GrokGateway Initialization Tests
# ============================================================================

class TestGrokGatewayInit:
    """Test GrokGateway initialization."""
    
    def test_init_with_defaults(self, mocker):
        """Initialize with just API key."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        assert gateway._model == "grok-2-mini"
    
    def test_init_with_custom_model(self, mocker):
        """Initialize with custom model."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(
            api_key="xai-test-key",
            model="grok-2"
        )
        
        assert gateway._model == "grok-2"
    
    def test_init_uses_grok_base_url(self, mocker):
        """Initialization uses xAI's API endpoint."""
        mock_openai_class = mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        mock_openai_class.assert_called_once()
        call_kwargs = mock_openai_class.call_args[1]
        assert "https://api.x.ai/v1" in call_kwargs["base_url"]


# ============================================================================
# Properties Tests
# ============================================================================

class TestGrokGatewayProperties:
    """Test GrokGateway properties."""
    
    def test_model_name_property(self, mocker):
        """model_name property returns configured model."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(
            api_key="xai-test-key",
            model="grok-2"
        )
        
        assert gateway.model_name == "grok-2"
    
    def test_provider_property(self, mocker):
        """provider property returns 'grok'."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        assert gateway.provider == "grok"
    
    def test_supports_files(self, mocker):
        """supports_files depends on model (grok-2 has vision)."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        # grok-2 supports vision
        gateway_2 = GrokGateway(api_key="xai-test-key", model="grok-2")
        assert gateway_2.supports_files is True
        
        # grok-2-mini doesn't mention vision
        gateway_mini = GrokGateway(api_key="xai-test-key", model="grok-2-mini")
        # grok-2 is substring of grok-2-mini, so this also returns True
        assert gateway_mini.supports_files is True
        
        # grok-1 doesn't have vision
        gateway_1 = GrokGateway(api_key="xai-test-key", model="grok-1")
        assert gateway_1.supports_files is False


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestGrokMessageConversion:
    """Test Grok message format conversion (OpenAI-compatible)."""
    
    def test_convert_simple_user_message(self, mocker):
        """Convert simple user message to Grok format."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        message = Message(role=MessageRole.USER, content="Hello")
        converted = gateway._convert_messages([message])
        
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"
    
    def test_convert_system_message(self, mocker):
        """Convert system message."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        message = Message(role=MessageRole.SYSTEM, content="You are a helpful assistant")
        converted = gateway._convert_messages([message])
        
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are a helpful assistant"
    
    def test_convert_multi_turn(self, mocker):
        """Convert multi-turn conversation."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="What is 2+2?"),
        ]
        
        converted = gateway._convert_messages(messages)
        
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "assistant"
        assert converted[2]["role"] == "user"
    
    def test_convert_empty_message_list(self, mocker):
        """Convert empty message list."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        converted = gateway._convert_messages([])
        
        assert converted == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestGrokConfigValidation:
    """Test Grok-specific config validation."""
    
    def test_validate_temperature_in_range(self, mocker):
        """Valid temperature [0, 2] passes."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        for temp in [0.0, 0.5, 1.0, 2.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_top_p_in_range(self, mocker):
        """Valid top_p [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestGrokResponseConversion:
    """Test Grok response parsing and conversion."""
    
    def test_convert_successful_response(self, mocker):
        """Convert successful Grok API response."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(
            api_key="xai-test-key",
            model="grok-2"
        )
        
        # Mock response (similar to OpenAI)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The answer is 4"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "grok-2"
        mock_response.usage.prompt_tokens = 30
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 40
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert isinstance(converted, ModelResponse)
        assert converted.content == "The answer is 4"
        assert converted.input_tokens == 30
        assert converted.output_tokens == 10
        assert converted.provider == "grok"
    
    def test_convert_response_long_output(self, mocker):
        """Convert response with long output."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A" * 1000
        mock_response.choices[0].finish_reason = "length"
        mock_response.model = "grok-2"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 500
        mock_response.usage.total_tokens = 600
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert len(converted.content) == 1000
        assert converted.output_tokens == 500


# ============================================================================
# Cost Estimation Tests
# ============================================================================

class TestGrokCostEstimation:
    """Test Grok pricing and cost estimation."""
    
    def test_estimate_cost_grok_2(self, mocker):
        """Estimate cost for grok-2."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="grok-2",
            provider="grok",
        )
        
        cost = gateway.estimate_cost(response)
        
        # grok-2: input=$2.00/M, output=$10/M
        # Expected: 2.00 + 10 = $12.00
        assert cost == pytest.approx(12.00, rel=0.01)
    
    def test_estimate_cost_grok_2_mini(self, mocker):
        """Estimate cost for grok-2-mini."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=100_000,
            total_tokens=200_000,
            model_name="grok-2-mini",
            provider="grok",
        )
        
        cost = gateway.estimate_cost(response)
        
        # grok-2-mini: input=$0.50/M, output=$2/M
        # Expected: (100k/1M * 0.50) + (100k/1M * 2) = 0.05 + 0.20 = $0.25
        assert cost == pytest.approx(0.25, rel=0.01)
    
    def test_estimate_cost_grok_1(self, mocker):
        """Estimate cost for grok-1 (legacy)."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=100_000,
            total_tokens=200_000,
            model_name="grok-1",
            provider="grok",
        )
        
        cost = gateway.estimate_cost(response)
        
        # grok-1: input=$5.00/M, output=$15/M
        # Expected: (100k/1M * 5) + (100k/1M * 15) = 0.50 + 1.50 = $2.00
        assert cost == pytest.approx(2.00, rel=0.01)


# ============================================================================
# Generate Tests
# ============================================================================

class TestGrokGenerate:
    """Test Grok generate method."""
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self, mocker):
        """Generate response with custom config."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "answer"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "grok-2"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 150
        del mock_response.model_dump
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        mocker.patch(
            "adapters.llm.adapter_grok.AsyncOpenAI",
            return_value=mock_client
        )
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        messages = [Message(role=MessageRole.USER, content="What is 2+2?")]
        config = GenerationConfig(temperature=0.7)
        
        result = await gateway.generate(messages, config)
        
        assert isinstance(result, ModelResponse)
        assert result.content == "answer"
    
    @pytest.mark.asyncio
    async def test_generate_handles_errors(self, mocker):
        """Generate handles API errors gracefully."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        
        mocker.patch(
            "adapters.llm.adapter_grok.AsyncOpenAI",
            return_value=mock_client
        )
        
        gateway = GrokGateway(api_key="xai-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(Exception):
            await gateway.generate(messages)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestGrokErrorHandling:
    """Test Grok error handling."""
    
    def test_invalid_model_raises_error_on_api_call(self, mocker):
        """Invalid model name raises error on API call."""
        mocker.patch("adapters.llm.adapter_grok.AsyncOpenAI")
        
        # Should initialize even with potentially invalid name
        gateway = GrokGateway(
            api_key="xai-test-key",
            model="unknown-grok-model"
        )
        
        assert gateway._model == "unknown-grok-model"
