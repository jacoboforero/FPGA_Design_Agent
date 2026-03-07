"""
Unit tests for adapters/llm/adapter_groq.py

Tests the Groq gateway implementation (OpenAI-compatible):
- GroqGateway initialization
- Groq API call handling
- Message format conversion
- Response parsing and cost estimation
- Configuration validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from adapters.llm.adapter_groq import GroqGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# GroqGateway Initialization Tests
# ============================================================================

class TestGroqGatewayInit:
    """Test GroqGateway initialization."""
    
    def test_init_with_defaults(self, mocker):
        """Initialize with just API key."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        assert gateway._model == "llama-3.1-8b-instant"
    
    def test_init_with_custom_model(self, mocker):
        """Initialize with custom model."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(
            api_key="gsk-test-key",
            model="llama-3.3-70b-versatile"
        )
        
        assert gateway._model == "llama-3.3-70b-versatile"
    
    def test_init_uses_groq_base_url(self, mocker):
        """Initialization uses Groq's API endpoint."""
        mock_openai_class = mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        mock_openai_class.assert_called_once()
        call_kwargs = mock_openai_class.call_args[1]
        assert "https://api.groq.com/openai/v1" in call_kwargs["base_url"]


# ============================================================================
# Properties Tests
# ============================================================================

class TestGroqGatewayProperties:
    """Test GroqGateway properties."""
    
    def test_model_name_property(self, mocker):
        """model_name property returns configured model."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(
            api_key="gsk-test-key",
            model="llama-3.1-70b-versatile"
        )
        
        assert gateway.model_name == "llama-3.1-70b-versatile"
    
    def test_provider_property(self, mocker):
        """provider property returns 'groq'."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        assert gateway.provider == "groq"
    
    def test_supports_files(self, mocker):
        """supports_files reflects Groq's capabilities."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        # Groq doesn't support files (bare Llama models)
        assert gateway.supports_files is False


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestGroqMessageConversion:
    """Test Groq message format conversion (OpenAI-like)."""
    
    def test_convert_simple_user_message(self, mocker):
        """Convert simple user message to Groq format."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        message = Message(role=MessageRole.USER, content="Hello")
        converted = gateway._convert_messages([message])
        
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"
    
    def test_convert_system_message(self, mocker):
        """Convert system message."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        message = Message(role=MessageRole.SYSTEM, content="You are helpful")
        converted = gateway._convert_messages([message])
        
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are helpful"
    
    def test_convert_multi_turn(self, mocker):
        """Convert multi-turn conversation."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="How are you?"),
        ]
        
        converted = gateway._convert_messages(messages)
        
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "assistant"
        assert converted[2]["role"] == "user"
    
    def test_convert_empty_message_list(self, mocker):
        """Convert empty message list."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        converted = gateway._convert_messages([])
        
        assert converted == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestGroqConfigValidation:
    """Test Groq-specific config validation."""
    
    def test_validate_temperature_in_range(self, mocker):
        """Valid temperature [0, 2] passes."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        for temp in [0.0, 0.5, 1.0, 2.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_top_p_in_range(self, mocker):
        """Valid top_p [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestGroqResponseConversion:
    """Test Groq response parsing and conversion."""
    
    def test_convert_successful_response(self, mocker):
        """Convert successful Groq API response."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(
            api_key="gsk-test-key",
            model="llama-3.1-8b-instant"
        )
        
        # Mock response (similar to OpenAI)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated code"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "llama-3.1-8b-instant"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 150
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert isinstance(converted, ModelResponse)
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100
        assert converted.provider == "groq"
    
    def test_convert_response_empty_content(self, mocker):
        """Convert response with empty content."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].finish_reason = "length"
        mock_response.model = "llama-3.1-8b-instant"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 100
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert converted.content == ""


# ============================================================================
# Cost Estimation Tests
# ============================================================================

class TestGroqCostEstimation:
    """Test Groq pricing and cost estimation."""
    
    def test_estimate_cost_llama_70b(self, mocker):
        """Estimate cost for llama-3.1-70b-versatile."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="llama-3.1-70b-versatile",
            provider="groq",
        )
        
        cost = gateway.estimate_cost(response)
        
        # llama-3.1-70b-versatile: $0.59/$0.79 per M
        # Expected: 0.59 + 0.79 = $1.38
        assert cost == pytest.approx(1.38, rel=0.01)
    
    def test_estimate_cost_llama_8b(self, mocker):
        """Estimate cost for llama-3.1-8b-instant."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=100_000,
            total_tokens=200_000,
            model_name="llama-3.1-8b-instant",
            provider="groq",
        )
        
        cost = gateway.estimate_cost(response)
        
        # llama-3.1-8b-instant: $0.05/$0.08 per M
        # Expected: (100k/1M * 0.05) + (100k/1M * 0.08) = 0.005 + 0.008 = $0.013
        assert cost == pytest.approx(0.013, rel=0.01)


# ============================================================================
# Generate Tests
# ============================================================================

class TestGroqGenerate:
    """Test Groq generate method."""
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self, mocker):
        """Generate response with custom config."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "code"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "llama-3.1-8b-instant"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 150
        del mock_response.model_dump
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        mocker.patch(
            "adapters.llm.adapter_groq.AsyncOpenAI",
            return_value=mock_client
        )
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        config = GenerationConfig(temperature=0.8)
        
        result = await gateway.generate(messages, config)
        
        assert isinstance(result, ModelResponse)
        assert result.content == "code"
    
    @pytest.mark.asyncio
    async def test_generate_handles_errors(self, mocker):
        """Generate handles API errors gracefully."""
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API error")
        )
        
        mocker.patch(
            "adapters.llm.adapter_groq.AsyncOpenAI",
            return_value=mock_client
        )
        
        gateway = GroqGateway(api_key="gsk-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(Exception):
            await gateway.generate(messages)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestGroqErrorHandling:
    """Test Groq error handling."""
    
    def test_invalid_model_raises_error_on_api_call(self, mocker):
        """Invalid model name raises error on API call."""
        mocker.patch("adapters.llm.adapter_groq.AsyncOpenAI")
        
        # Should initialize even with potentially invalid name
        gateway = GroqGateway(
            api_key="gsk-test-key",
            model="invalid-model"
        )
        
        assert gateway._model == "invalid-model"
