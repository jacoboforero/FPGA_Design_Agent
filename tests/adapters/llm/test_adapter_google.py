"""
Unit tests for adapters/llm/adapter_google.py

Tests the Google Gemini gateway implementation:
- GoogleGeminiGateway initialization
- Gemini API call handling
- Message format conversion
- Response parsing and cost estimation
- Configuration validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from adapters.llm.adapter_google import GoogleGeminiGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# GoogleGeminiGateway Initialization Tests
# ============================================================================

class TestGoogleGeminiGatewayInit:
    """Test GoogleGeminiGateway initialization."""
    
    def test_init_with_defaults(self, mocker):
        """Initialize with just API key."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        assert gateway._model_name == "gemini-2.0-flash"
    
    def test_init_with_custom_model(self, mocker):
        """Initialize with custom model."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(
            api_key="AIzaSyExample",
            model="gemini-1.5-pro"
        )
        
        assert gateway._model_name == "gemini-1.5-pro"
    
    def test_init_configures_api_key(self, mocker):
        """Initialization configures API key."""
        mock_configure = mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        mock_configure.assert_called_once_with(api_key="AIzaSyExample")
    
    def test_init_creates_model(self, mocker):
        """Initialization creates GenerativeModel."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mock_model_class = mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        mock_model_class.assert_called_once_with("gemini-2.0-flash")


# ============================================================================
# Properties Tests
# ============================================================================

class TestGoogleGeminiGatewayProperties:
    """Test GoogleGeminiGateway properties."""
    
    def test_model_name_property(self, mocker):
        """model_name property returns configured model."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(
            api_key="AIzaSyExample",
            model="gemini-1.5-pro"
        )
        
        assert gateway.model_name == "gemini-1.5-pro"
    
    def test_provider_property(self, mocker):
        """provider property returns 'google'."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        assert gateway.provider == "google"
    
    def test_supports_files(self, mocker):
        """supports_files is True for Gemini models."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        assert gateway.supports_files is True


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestGoogleGeminiMessageConversion:
    """Test Google Gemini message format conversion."""
    
    def test_convert_simple_user_message(self, mocker):
        """Convert simple user message to Gemini format."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        message = Message(role=MessageRole.USER, content="Hello")
        messages, system = gateway._convert_messages([message])
        
        assert system is None
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "Hello" in str(messages[0]["parts"])
    
    def test_convert_with_system_instruction(self, mocker):
        """System message extracted as system_instruction."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant"),
            Message(role=MessageRole.USER, content="Hello"),
        ]
        
        converted, system = gateway._convert_messages(messages)
        
        assert system == "You are a helpful assistant"
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
    
    def test_convert_multi_turn(self, mocker):
        """Convert multi-turn conversation."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="How are you?"),
        ]
        
        converted, system = gateway._convert_messages(messages)
        
        assert system is None
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        # Gemini converts ASSISTANT to "model"
        assert converted[1]["role"] == "model"
        assert converted[2]["role"] == "user"
    
    def test_convert_empty_message_list(self, mocker):
        """Convert empty message list."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        messages, system = gateway._convert_messages([])
        
        assert system is None
        assert messages == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestGoogleGeminiConfigValidation:
    """Test Google Gemini-specific config validation."""
    
    def test_validate_temperature_in_range(self, mocker):
        """Valid temperature [0, 2] passes."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        for temp in [0.0, 0.5, 1.0, 2.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_top_p_in_range(self, mocker):
        """Valid top_p [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9
    
    def test_validate_top_k_supported(self, mocker):
        """top_k is supported by Gemini."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        config = GenerationConfig(top_k=40)
        validated = gateway.validate_config(config)
        assert validated.top_k == 40


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestGoogleGeminiResponseConversion:
    """Test Google Gemini response parsing and conversion."""
    
    def test_convert_successful_response(self, mocker):
        """Convert successful Gemini API response."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(
            api_key="AIzaSyExample",
            model="gemini-2.0-flash"
        )
        
        # Mock response
        mock_response = MagicMock()
        mock_response.text = "Generated code"
        mock_response.candidates = [MagicMock(finish_reason="STOP")]
        mock_response.usage_metadata.prompt_token_count = 50
        mock_response.usage_metadata.candidates_token_count = 100
        mock_response.to_dict = MagicMock(return_value={})
        
        converted = gateway._convert_response(mock_response)
        
        assert isinstance(converted, ModelResponse)
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100
        assert converted.provider == "google"
    
    def test_convert_response_empty_content(self, mocker):
        """Convert response with empty string content."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 100
        mock_usage.candidates_token_count = 50
        
        mock_candidate = MagicMock()
        mock_candidate.finish_reason = "MAX_TOKENS"
        
        mock_response = MagicMock()
        mock_response.text = ""  # Empty string instead of None
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = mock_usage
        mock_response.to_dict = MagicMock(return_value={})
        
        converted = gateway._convert_response(mock_response)
        
        assert converted.content == ""


# ============================================================================
# Cost Estimation Tests
# ============================================================================

class TestGoogleGeminiCostEstimation:
    """Test Google Gemini pricing and cost estimation."""
    
    def test_estimate_cost_gemini_2_pro(self, mocker):
        """Estimate cost for gemini-2.0-pro."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="gemini-2.0-pro",
            provider="google",
        )
        
        cost = gateway.estimate_cost(response)
        
        # gemini-2.0-pro: input=$1.25/M, output=$5/M
        # Expected: 1.25 + 5 = $6.25
        assert cost == pytest.approx(6.25, rel=0.01)
    
    def test_estimate_cost_gemini_flash(self, mocker):
        """Estimate cost for gemini-2.0-flash."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=100_000,
            total_tokens=200_000,
            model_name="gemini-2.0-flash",
            provider="google",
        )
        
        cost = gateway.estimate_cost(response)
        
        # gemini-2.0-flash: input=$0.075/M, output=$0.30/M
        # Expected: (100k/1M * 0.075) + (100k/1M * 0.30) = 0.0075 + 0.03 = $0.0375
        assert cost == pytest.approx(0.0375, rel=0.01)
    
    def test_estimate_cost_gemini_1_pro(self, mocker):
        """Estimate cost for gemini-1.5-pro."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="gemini-1.5-pro",
            provider="google",
        )
        
        cost = gateway.estimate_cost(response)
        
        # gemini-1.5-pro: input=$1.25/M, output=$5/M
        assert cost == pytest.approx(6.25, rel=0.01)


# ============================================================================
# Generate Tests
# ============================================================================

class TestGoogleGeminiGenerate:
    """Test Google Gemini generate method."""
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self, mocker):
        """Generate response with custom config."""
        mock_model = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "Generated code"
        mock_response.candidates = [MagicMock(finish_reason="STOP")]
        mock_response.usage_metadata.prompt_token_count = 50
        mock_response.usage_metadata.candidates_token_count = 100
        mock_response.to_dict = MagicMock(return_value={})
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch(
            "adapters.llm.adapter_google.genai.GenerativeModel",
            return_value=mock_model
        )
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        config = GenerationConfig(temperature=0.8, max_tokens=500)
        
        result = await gateway.generate(messages, config)
        
        assert isinstance(result, ModelResponse)
        assert result.content == "Generated code"
    
    @pytest.mark.asyncio
    async def test_generate_handles_errors(self, mocker):
        """Generate handles API errors gracefully."""
        mock_model = AsyncMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=Exception("API error")
        )
        
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch(
            "adapters.llm.adapter_google.genai.GenerativeModel",
            return_value=mock_model
        )
        
        gateway = GoogleGeminiGateway(api_key="AIzaSyExample")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(Exception):
            await gateway.generate(messages)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestGoogleGeminiErrorHandling:
    """Test Google Gemini error handling."""
    
    def test_missing_api_key_environment(self, mocker):
        """Missing API key is handled by genai.configure."""
        mock_configure = mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        # Should pass None to configure if not provided
        gateway = GoogleGeminiGateway(api_key="test-key")
        
        mock_configure.assert_called_once_with(api_key="test-key")
    
    def test_invalid_model_raises_error_on_api_call(self, mocker):
        """Invalid model name raises error on API call."""
        mocker.patch("adapters.llm.adapter_google.genai.configure")
        mocker.patch("adapters.llm.adapter_google.genai.GenerativeModel")
        
        # Should initialize even with potentially invalid name
        gateway = GoogleGeminiGateway(
            api_key="AIzaSyExample",
            model="invalid-model"
        )
        
        assert gateway._model_name == "invalid-model"
