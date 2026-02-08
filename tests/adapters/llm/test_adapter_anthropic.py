"""
Unit tests for adapters/llm/adapter_anthropic.py

Tests the Anthropic Claude gateway implementation:
- AnthropicGateway initialization
- Claude API call handling
- Message format conversion (system messages separate)
- Response parsing and cost estimation
- Configuration validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from adapters.llm.adapter_anthropic import AnthropicGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# AnthropicGateway Initialization Tests
# ============================================================================

class TestAnthropicGatewayInit:
    """Test AnthropicGateway initialization."""
    
    def test_init_with_defaults(self, mocker):
        """Initialize with just API key."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        assert gateway._model == "claude-sonnet-4-5-20250929"
    
    def test_init_with_custom_model(self, mocker):
        """Initialize with custom model."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="claude-opus-4-5-20250514"
        )
        
        assert gateway._model == "claude-opus-4-5-20250514"
    
    def test_init_creates_async_client(self, mocker):
        """Initialization creates AsyncAnthropic client."""
        mock_anthropic_class = mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        mock_anthropic_class.assert_called_once_with(api_key="sk-ant-test-key")


# ============================================================================
# Properties Tests
# ============================================================================

class TestAnthropicGatewayProperties:
    """Test AnthropicGateway properties."""
    
    def test_model_name_property(self, mocker):
        """model_name property returns configured model."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="claude-opus-4-5-20250514"
        )
        
        assert gateway.model_name == "claude-opus-4-5-20250514"
    
    def test_provider_property(self, mocker):
        """provider property returns 'anthropic'."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        assert gateway.provider == "anthropic"
    
    def test_supports_files_for_claude3(self, mocker):
        """supports_files is True for Claude 3+ models."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        # Claude 3+ models have vision support
        gateway_3 = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="claude-3-opus-20240229"
        )
        assert gateway_3.supports_files is True
        
        # Claude 4 models have vision support
        gateway_4 = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="claude-4-20250514"
        )
        assert gateway_4.supports_files is True
        
        # Older models don't have vision
        gateway_old = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="claude-2"
        )
        assert gateway_old.supports_files is False


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestAnthropicMessageConversion:
    """Test Anthropic message format conversion (system separate)."""
    
    def test_convert_simple_user_message(self, mocker):
        """Convert simple user message to Anthropic format."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        message = Message(role=MessageRole.USER, content="Hello")
        system, messages = gateway._convert_messages([message])
        
        assert system == ""  # Empty string when no system message
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
    
    def test_convert_with_system_message(self, mocker):
        """System message extracted separately."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="Hello"),
        ]
        
        system, converted = gateway._convert_messages(messages)
        
        assert system == "You are helpful"
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
    
    def test_convert_multi_turn(self, mocker):
        """Convert multi-turn conversation."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="How are you?"),
        ]
        
        system, converted = gateway._convert_messages(messages)
        
        assert system == ""  # No system messages
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "assistant"
        assert converted[2]["role"] == "user"
    
    def test_convert_message_with_attachments(self, mocker):
        """Convert message with file attachments."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        message = Message(
            role=MessageRole.USER,
            content="Analyze this:",
            attachments=[
                {"filename": "design.v", "content": "module test();endmodule"},
            ]
        )
        
        system, converted = gateway._convert_messages([message])
        
        assert len(converted) == 1
        content = converted[0]["content"]
        assert "Analyze this:" in content
        assert "design.v" in content
    
    def test_convert_empty_message_list(self, mocker):
        """Convert empty message list."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        system, converted = gateway._convert_messages([])
        
        assert system == ""  # Empty string when no system
        assert converted == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestAnthropicConfigValidation:
    """Test Anthropic-specific config validation."""
    
    def test_validate_temperature_in_range(self, mocker):
        """Valid temperature [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        for temp in [0.0, 0.5, 1.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_temperature_too_high(self, mocker):
        """Temperature above 1 raises error."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        config = GenerationConfig(temperature=1.1)
        with pytest.raises(ValueError, match="temperature"):
            gateway.validate_config(config)
    
    def test_validate_top_p_in_range(self, mocker):
        """Valid top_p [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9
    
    def test_validate_top_k_supported(self, mocker):
        """top_k is supported by Anthropic."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        config = GenerationConfig(top_k=40)
        validated = gateway.validate_config(config)
        assert validated.top_k == 40


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestAnthropicResponseConversion:
    """Test Anthropic response parsing and conversion."""
    
    def test_convert_successful_response(self, mocker):
        """Convert successful Anthropic API response."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="claude-3-opus-20240229"
        )
        
        # Mock response with model_dump method
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Generated code"
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-3-opus-20240229"
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 100
        mock_response.model_dump = MagicMock(return_value={})
        
        converted = gateway._convert_response(mock_response)
        
        assert isinstance(converted, ModelResponse)
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100
        assert converted.total_tokens == 150
        assert converted.provider == "anthropic"
    
    def test_convert_response_with_text_blocks(self, mocker):
        """Convert response with multiple content blocks."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Part 1"),
            MagicMock(text="Part 2"),
        ]
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-3-opus"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20
        mock_response.model_dump = MagicMock(return_value={})
        
        converted = gateway._convert_response(mock_response)
        
        # Should concatenate text blocks
        assert "Part 1" in converted.content
        assert "Part 2" in converted.content


# ============================================================================
# Cost Estimation Tests
# ============================================================================

class TestAnthropicCostEstimation:
    """Test Anthropic pricing and cost estimation."""
    
    def test_estimate_cost_claude_opus(self, mocker):
        """Estimate cost for claude-opus-4-5."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="claude-opus-4-5",
            provider="anthropic",
        )
        
        cost = gateway.estimate_cost(response)
        
        # claude-opus-4-5: input=$15/M, output=$75/M
        # Expected: (1 * 15) + (1 * 75) = $90
        assert cost == pytest.approx(90.0, rel=0.01)
    
    def test_estimate_cost_claude_sonnet(self, mocker):
        """Estimate cost for claude-sonnet-4-5."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="claude-sonnet-4-5",
            provider="anthropic",
        )
        
        cost = gateway.estimate_cost(response)
        
        # claude-sonnet-4-5: input=$3/M, output=$15/M
        # Expected: 3 + 15 = $18
        assert cost == pytest.approx(18.0, rel=0.01)
    
    def test_estimate_cost_claude_haiku(self, mocker):
        """Estimate cost for claude-haiku-4-5."""
        mocker.patch("adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic")
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=100_000,
            total_tokens=200_000,
            model_name="claude-haiku-4-5",
            provider="anthropic",
        )
        
        cost = gateway.estimate_cost(response)
        
        # claude-haiku-4-5: input=$0.80/M, output=$4/M
        # Expected: (100k/1M * 0.80) + (100k/1M * 4) = 0.08 + 0.40 = $0.48
        assert cost == pytest.approx(0.48, rel=0.01)


# ============================================================================
# Generate Tests
# ============================================================================

class TestAnthropicGenerate:
    """Test Anthropic generate method."""
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self, mocker):
        """Generate response with custom config."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="code")]
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-3-opus"
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 100
        mock_response.model_dump = MagicMock(return_value={})
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        
        mocker.patch(
            "adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic",
            return_value=mock_client
        )
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        config = GenerationConfig(temperature=0.8, max_tokens=500)
        
        result = await gateway.generate(messages, config)
        
        assert isinstance(result, ModelResponse)
        assert result.content == "code"
        mock_client.messages.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_handles_errors(self, mocker):
        """Generate handles API errors gracefully."""
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API error")
        )
        
        mocker.patch(
            "adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic",
            return_value=mock_client
        )
        
        gateway = AnthropicGateway(api_key="sk-ant-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(Exception):
            await gateway.generate(messages)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestAnthropicErrorHandling:
    """Test Anthropic error handling."""
    
    def test_invalid_model_raises_error(self, mocker):
        """Invalid model name raises error on first API call."""
        mock_client = AsyncMock()
        mocker.patch(
            "adapters.llm.adapter_anthropic.anthropic.AsyncAnthropic",
            return_value=mock_client
        )
        
        # Should initialize even with potentially invalid name
        # Error only on API call
        gateway = AnthropicGateway(
            api_key="sk-ant-test-key",
            model="invalid-model"
        )
        
        assert gateway._model == "invalid-model"
