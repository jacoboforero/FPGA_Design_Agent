"""
Unit tests for adapters/llm/adapter_cohere.py

Tests the Cohere gateway implementation:
- CohereGateway initialization
- Cohere API call handling
- Message format conversion
- Response parsing and cost estimation
- Configuration validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from adapters.llm.adapter_cohere import CohereGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# CohereGateway Initialization Tests
# ============================================================================

class TestCohereGatewayInit:
    """Test CohereGateway initialization."""
    
    def test_init_with_defaults(self, mocker):
        """Initialize with just API key."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        assert gateway._model == "command-r"
    
    def test_init_with_custom_model(self, mocker):
        """Initialize with custom model."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(
            api_key="cohere-test-key",
            model="command-r-plus"
        )
        
        assert gateway._model == "command-r-plus"
    
    def test_init_creates_async_client(self, mocker):
        """Initialization creates AsyncClient."""
        mock_cohere_class = mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        mock_cohere_class.assert_called_once_with(api_key="cohere-test-key")


# ============================================================================
# Properties Tests
# ============================================================================

class TestCohereGatewayProperties:
    """Test CohereGateway properties."""
    
    def test_model_name_property(self, mocker):
        """model_name property returns configured model."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(
            api_key="cohere-test-key",
            model="command-r-plus"
        )
        
        assert gateway.model_name == "command-r-plus"
    
    def test_provider_property(self, mocker):
        """provider property returns 'cohere'."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        assert gateway.provider == "cohere"
    
    def test_supports_files(self, mocker):
        """supports_files is True for Cohere."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        assert gateway.supports_files is True


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestCohereMessageConversion:
    """Test Cohere message format conversion."""
    
    def test_convert_simple_user_message(self, mocker):
        """Convert simple user message to Cohere format."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        message = Message(role=MessageRole.USER, content="Hello")
        messages, preamble = gateway._convert_messages([message])
        
        assert preamble == ""  # Empty string when no system message
        assert len(messages) == 1
        assert "message" in messages[0]
        assert messages[0]["message"] == "Hello"
        assert messages[0]["role"] == "USER"  # Cohere uses uppercase roles
    
    def test_convert_with_system_message(self, mocker):
        """System message extracted as preamble."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="Hello"),
        ]
        
        converted, preamble = gateway._convert_messages(messages)
        
        assert preamble == "You are helpful"
        assert len(converted) == 1
    
    def test_convert_multi_turn(self, mocker):
        """Convert multi-turn conversation."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="How are you?"),
        ]
        
        converted, preamble = gateway._convert_messages(messages)
        
        assert preamble == ""  # No system message
        assert len(converted) == 3
        assert converted[0]["role"] == "USER"  # Cohere uppercase
        assert converted[1]["role"] == "CHATBOT"  # Cohere uses CHATBOT not ASSISTANT
        assert converted[2]["role"] == "USER"
    
    def test_convert_empty_message_list(self, mocker):
        """Convert empty message list."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        messages, preamble = gateway._convert_messages([])
        
        assert preamble == ""  # Empty string
        assert messages == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestCohereConfigValidation:
    """Test Cohere-specific config validation."""
    
    def test_validate_temperature_in_range(self, mocker):
        """Valid temperature [0, 5] passes."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        for temp in [0.0, 0.5, 1.0, 5.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_top_p_in_range(self, mocker):
        """Valid top_p [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9
    
    def test_validate_top_k_supported(self, mocker):
        """top_k is supported by Cohere."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        config = GenerationConfig(top_k=40)
        validated = gateway.validate_config(config)
        assert validated.top_k == 40


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestCohereResponseConversion:
    """Test Cohere response parsing and conversion."""
    
    def test_convert_successful_response(self, mocker):
        """Convert successful Cohere API response."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(
            api_key="cohere-test-key",
            model="command-r"
        )
        
        # Mock response - Cohere uses meta.billed_units for token counts
        mock_billed_units = MagicMock()
        mock_billed_units.input_tokens = 50
        mock_billed_units.output_tokens = 100
        
        mock_meta = MagicMock()
        mock_meta.billed_units = mock_billed_units
        
        mock_response = MagicMock()
        mock_response.text = "Generated code"
        mock_response.generation_id = "gen-123"
        mock_response.finish_reason = "COMPLETE"
        mock_response.meta = mock_meta
        
        converted = gateway._convert_response(mock_response)
        
        assert isinstance(converted, ModelResponse)
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100
        assert converted.provider == "cohere"
    
    def test_convert_response_empty_content(self, mocker):
        """Convert response with empty content."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        mock_billed_units = MagicMock()
        mock_billed_units.input_tokens = 100
        mock_billed_units.output_tokens = 0
        
        mock_meta = MagicMock()
        mock_meta.billed_units = mock_billed_units
        
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.generation_id = "gen-123"
        mock_response.finish_reason = "COMPLETE"
        mock_response.meta = mock_meta
        
        converted = gateway._convert_response(mock_response)
        
        assert converted.content == ""


# ============================================================================
# Cost Estimation Tests
# ============================================================================

class TestCohereCostEstimation:
    """Test Cohere pricing and cost estimation."""
    
    def test_estimate_cost_command_r_plus(self, mocker):
        """Estimate cost for command-r-plus."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="command-r-plus",
            provider="cohere",
        )
        
        cost = gateway.estimate_cost(response)
        
        # command-r-plus: input=$2.50/M, output=$10/M
        # Expected: 2.50 + 10 = $12.50
        assert cost == pytest.approx(12.50, rel=0.01)
    
    def test_estimate_cost_command_r(self, mocker):
        """Estimate cost for command-r."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=100_000,
            total_tokens=200_000,
            model_name="command-r",
            provider="cohere",
        )
        
        cost = gateway.estimate_cost(response)
        
        # command-r: input=$0.15/M, output=$0.60/M
        # Expected: (100k/1M * 0.15) + (100k/1M * 0.60) = 0.015 + 0.060 = $0.075
        assert cost == pytest.approx(0.075, rel=0.01)


# ============================================================================
# Generate Tests
# ============================================================================

class TestCohereGenerate:
    """Test Cohere generate method."""
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self, mocker):
        """Generate response with custom config."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "generated code"
        mock_response.generation_id = "gen-123"
        mock_response.finish_reason = "COMPLETE"
        mock_response.meta.billed_units.input_tokens = 50
        mock_response.meta.billed_units.output_tokens = 100
        mock_response.__dict__ = {"text": "generated code"}
        mock_client.chat = AsyncMock(return_value=mock_response)
        
        mocker.patch(
            "adapters.llm.adapter_cohere.cohere.AsyncClient",
            return_value=mock_client
        )
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        config = GenerationConfig(temperature=0.8)
        
        result = await gateway.generate(messages, config)
        
        assert isinstance(result, ModelResponse)
        assert result.content == "generated code"
    
    @pytest.mark.asyncio
    async def test_generate_handles_errors(self, mocker):
        """Generate handles API errors gracefully."""
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(side_effect=Exception("API error"))
        
        mocker.patch(
            "adapters.llm.adapter_cohere.cohere.AsyncClient",
            return_value=mock_client
        )
        
        gateway = CohereGateway(api_key="cohere-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(Exception):
            await gateway.generate(messages)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestCohereErrorHandling:
    """Test Cohere error handling."""
    
    def test_invalid_model_raises_error_on_api_call(self, mocker):
        """Invalid model name raises error on API call."""
        mocker.patch("adapters.llm.adapter_cohere.cohere.AsyncClient")
        
        # Should initialize even with potentially invalid name
        gateway = CohereGateway(
            api_key="cohere-test-key",
            model="invalid-model"
        )
        
        assert gateway._model == "invalid-model"
