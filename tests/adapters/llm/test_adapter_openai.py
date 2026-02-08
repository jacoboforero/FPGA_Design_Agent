"""
Unit tests for adapters/llm/adapter_openai.py

Tests the OpenAI-specific gateway implementation:
- OpenAIGateway initialization
- OpenAI API call handling
- Message format conversion
- Response parsing and cost estimation
- Configuration validation
- Error handling and retries
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from adapters.llm.adapter_openai import OpenAIGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# OpenAIGateway Initialization Tests
# ============================================================================

class TestOpenAIGatewayInit:
    """Test OpenAIGateway initialization."""
    
    def test_init_with_defaults(self, mocker):
        """Initialize with just API key."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        assert gateway._model == "gpt-5-nano"
    
    def test_init_with_custom_model(self, mocker):
        """Initialize with custom model."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(
            api_key="sk-test-key",
            model="gpt-4o"
        )
        
        assert gateway._model == "gpt-4o"
    
    def test_init_with_organization(self, mocker):
        """Initialize with organization parameter."""
        mock_openai = mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(
            api_key="sk-test-key",
            model="gpt-4o",
            organization="org-123"
        )
        
        # Verify AsyncOpenAI was called with organization
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["organization"] == "org-123"
    
    def test_init_creates_async_client(self, mocker):
        """Initialization creates AsyncOpenAI client."""
        mock_openai_class = mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        mock_openai_class.assert_called_once()


# ============================================================================
# Properties Tests
# ============================================================================

class TestOpenAIGatewayProperties:
    """Test OpenAIGateway properties."""
    
    def test_model_name_property(self, mocker):
        """model_name property returns configured model."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key", model="gpt-4o-mini")
        
        assert gateway.model_name == "gpt-4o-mini"
    
    def test_provider_property(self, mocker):
        """provider property returns 'openai'."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        assert gateway.provider == "openai"
    
    def test_supports_files_for_vision_models(self, mocker):
        """supports_files is True for vision models."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway_vision = OpenAIGateway(api_key="sk-test-key", model="gpt-4-vision")
        assert gateway_vision.supports_files is True
        
        gateway_4o = OpenAIGateway(api_key="sk-test-key", model="gpt-4o")
        assert gateway_4o.supports_files is True
    
    def test_supports_files_for_text_models(self, mocker):
        """supports_files is False for text-only models."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key", model="gpt-4.1-nano")
        assert gateway.supports_files is False


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestOpenAIMessageConversion:
    """Test OpenAI message format conversion."""
    
    def test_convert_simple_user_message(self, mocker):
        """Convert simple user message to OpenAI format."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        message = Message(role=MessageRole.USER, content="Hello")
        converted = gateway._convert_messages([message])
        
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"
    
    def test_convert_multiple_messages(self, mocker):
        """Convert multi-turn conversation."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi there!"),
            Message(role=MessageRole.USER, content="How are you?"),
        ]
        
        converted = gateway._convert_messages(messages)
        
        assert len(converted) == 4
        assert converted[0]["role"] == "system"
        assert converted[1]["role"] == "user"
        assert converted[2]["role"] == "assistant"
        assert converted[3]["role"] == "user"
    
    def test_convert_message_with_inline_attachments(self, mocker):
        """Convert message with inline attachment content."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        message = Message(
            role=MessageRole.USER,
            content="Analyze this code:",
            attachments=[
                {"filename": "test.v", "content": "module test();endmodule"},
            ]
        )
        
        converted = gateway._convert_messages([message])
        
        assert len(converted) == 1
        content = converted[0]["content"]
        assert "Analyze this code:" in content
        assert "test.v" in content
        assert "module test();endmodule" in content
    
    def test_convert_message_with_path_attachments(self, mocker, tmp_path):
        """Convert message with file path attachments."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        # Create a temp file
        test_file = tmp_path / "test.v"
        test_file.write_text("module test();endmodule")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        message = Message(
            role=MessageRole.USER,
            content="Analyze:",
            attachments=[
                {"path": str(test_file), "filename": "test.v"},
            ]
        )
        
        converted = gateway._convert_messages([message])
        
        content = converted[0]["content"]
        assert "Analyze:" in content
        assert "test.v" in content
        assert "module test();endmodule" in content
    
    def test_convert_message_with_missing_attachment_file(self, mocker):
        """Handle missing attachment file gracefully."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        message = Message(
            role=MessageRole.USER,
            content="Check this:",
            attachments=[
                {"path": "/nonexistent/file.v", "filename": "file.v"},
            ]
        )
        
        converted = gateway._convert_messages([message])
        
        content = converted[0]["content"]
        assert "Check this:" in content
        # Should have error message
        assert "Error" in content
    
    def test_convert_message_attachment_without_filename(self, mocker):
        """Handle attachment without explicit filename."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        message = Message(
            role=MessageRole.USER,
            content="Look at:",
            attachments=[
                {"content": "some content"},
            ]
        )
        
        converted = gateway._convert_messages([message])
        
        content = converted[0]["content"]
        assert "Look at:" in content
        assert "file" in content.lower()  # Should use "file" as default
    
    def test_convert_empty_message_list(self, mocker):
        """Convert empty message list."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        converted = gateway._convert_messages([])
        
        assert converted == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestOpenAIConfigValidation:
    """Test OpenAI-specific config validation."""
    
    def test_validate_temperature_in_range(self, mocker):
        """Valid temperature [0, 2] passes."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        for temp in [0.0, 0.5, 1.0, 1.5, 2.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_temperature_too_low(self, mocker):
        """Temperature below 0 raises error."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(temperature=-0.1)
        with pytest.raises(ValueError, match="temperature.*0.*2"):
            gateway.validate_config(config)
    
    def test_validate_temperature_too_high(self, mocker):
        """Temperature above 2 raises error."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(temperature=2.1)
        with pytest.raises(ValueError, match="temperature.*0.*2"):
            gateway.validate_config(config)
    
    def test_validate_top_p_in_range(self, mocker):
        """Valid top_p [0, 1] passes."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        for p in [0.0, 0.5, 0.9, 1.0]:
            config = GenerationConfig(top_p=p)
            validated = gateway.validate_config(config)
            assert validated.top_p == p
    
    def test_validate_top_p_too_low(self, mocker):
        """top_p below 0 raises error."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(top_p=-0.1)
        with pytest.raises(ValueError, match="top_p.*0.*1"):
            gateway.validate_config(config)
    
    def test_validate_top_p_too_high(self, mocker):
        """top_p above 1 raises error."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(top_p=1.1)
        with pytest.raises(ValueError, match="top_p.*0.*1"):
            gateway.validate_config(config)
    
    def test_validate_top_k_not_supported(self, mocker):
        """top_k parameter raises error."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(top_k=40)
        with pytest.raises(ValueError, match="top_k"):
            gateway.validate_config(config)
    
    def test_validate_temperature_and_top_p_together(self, mocker):
        """Using both temperature and top_p logs warning."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(temperature=0.7, top_p=0.9)
        # Should not raise, but logs warning
        validated = gateway.validate_config(config)
        
        assert validated.temperature == 0.7
        assert validated.top_p == 0.9


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestOpenAIResponseConversion:
    """Test OpenAI response parsing and conversion."""
    
    def test_convert_successful_response(self, mocker):
        """Convert successful OpenAI API response."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key", model="gpt-4o")
        
        # Mock response object
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated code"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 150
        # Don't include model_dump if not in mock - _convert_response handles this
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert isinstance(converted, ModelResponse)
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100
        assert converted.total_tokens == 150
        assert converted.finish_reason == "stop"
        assert converted.model_name == "gpt-4o"
        assert converted.provider == "openai"
    
    def test_convert_response_empty_content(self, mocker):
        """Convert response with empty content."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].finish_reason = "length"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 100
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert converted.content == ""
        assert converted.finish_reason == "length"
    
    def test_convert_response_length_finish(self, mocker):
        """Response finished due to token limit."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Code..."
        mock_response.choices[0].finish_reason = "length"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 2000
        mock_response.usage.total_tokens = 2050
        del mock_response.model_dump
        
        converted = gateway._convert_response(mock_response)
        
        assert converted.finish_reason == "length"
        assert converted.output_tokens == 2000


# ============================================================================
# Cost Estimation Tests
# ============================================================================

class TestOpenAICostEstimation:
    """Test OpenAI pricing and cost estimation."""
    
    def test_estimate_cost_gpt4o(self, mocker):
        """Estimate cost for gpt-4o model."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="gpt-4o",
            provider="openai",
        )
        
        cost = gateway.estimate_cost(response)
        
        # gpt-4o: input=$2.50/M, output=$10/M
        # Expected: (1 * 2.50) + (1 * 10) = $12.50
        assert cost == pytest.approx(12.50, rel=0.01)
    
    def test_estimate_cost_gpt4o_mini(self, mocker):
        """Estimate cost for gpt-4o-mini."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            model_name="gpt-4o-mini",
            provider="openai",
        )
        
        cost = gateway.estimate_cost(response)
        
        # gpt-4o-mini: input=$0.15/M, output=$0.60/M
        # Expected: 0.15 + 0.60 = $0.75
        assert cost == pytest.approx(0.75, rel=0.01)
    
    def test_estimate_cost_gpt4_1(self, mocker):
        """Estimate cost for gpt-4.1."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100_000,
            output_tokens=200_000,
            total_tokens=300_000,
            model_name="gpt-4.1",
            provider="openai",
        )
        
        cost = gateway.estimate_cost(response)
        
        # gpt-4.1: input=$2.00/M, output=$8.00/M
        # Expected: (100k/1M * 2) + (200k/1M * 8) = 0.20 + 1.60 = $1.80
        assert cost == pytest.approx(1.80, rel=0.01)
    
    def test_estimate_cost_unknown_model(self, mocker):
        """Unknown model returns 0 cost and logs warning."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        response = ModelResponse(
            content="test",
            input_tokens=100,
            output_tokens=100,
            total_tokens=200,
            model_name="unknown-model-xyz",
            provider="openai",
        )
        
        cost = gateway.estimate_cost(response)
        
        # Unknown model should return 0
        assert cost == 0.0
    
    def test_estimate_cost_zero_tokens(self, mocker):
        """Cost is 0 for zero tokens."""
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI")
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        response = ModelResponse(
            content="",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            model_name="gpt-4o",
            provider="openai",
        )
        
        cost = gateway.estimate_cost(response)
        
        assert cost == 0.0


# ============================================================================
# Generate Method Tests
# ============================================================================

class TestOpenAIGenerate:
    """Test the main generate() method."""
    
    @pytest.mark.asyncio
    async def test_generate_success(self, mocker):
        """Successful generate() call."""
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated code"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 150
        # Remove model_dump to test handling of response without it
        if hasattr(mock_response, 'model_dump'):
            del mock_response.model_dump
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        gateway = OpenAIGateway(api_key="sk-test-key", model="gpt-4o")
        
        messages = [Message(role=MessageRole.USER, content="Generate code")]
        response = await gateway.generate(messages)
        
        assert response.content == "Generated code"
        assert response.provider == "openai"
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self, mocker):
        """generate() passes config parameters to API."""
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "result"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        if hasattr(mock_response, 'model_dump'):
            del mock_response.model_dump
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(
            temperature=0.7,
            top_p=0.9,
            max_tokens=500,
            stop_sequences=["STOP"]
        )
        
        messages = [Message(role=MessageRole.USER, content="test")]
        await gateway.generate(messages, config)
        
        # Verify API was called with correct params
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["top_p"] == 0.9
        assert call_kwargs["max_tokens"] == 500
        assert call_kwargs["stop"] == ["STOP"]
    
    @pytest.mark.asyncio
    async def test_generate_with_provider_specific_params(self, mocker):
        """generate() includes provider_specific parameters."""
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "result"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30
        if hasattr(mock_response, 'model_dump'):
            del mock_response.model_dump
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        config = GenerationConfig(
            provider_specific={"logprobs": 10, "top_logprobs": 3}
        )
        
        messages = [Message(role=MessageRole.USER, content="test")]
        await gateway.generate(messages, config)
        
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["logprobs"] == 10
        assert call_kwargs["top_logprobs"] == 3
    
    @pytest.mark.asyncio
    async def test_generate_handles_rate_limit(self, mocker):
        """generate() translates rate limit errors."""
        from openai import RateLimitError
        from unittest.mock import MagicMock
        
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        # Create a proper mock response for the error
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        
        error = RateLimitError("Rate limit exceeded", response=mock_response, body={})
        mock_client.chat.completions.create = AsyncMock(side_effect=error)
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(RuntimeError, match="rate limit"):
            await gateway.generate(messages)
    
    @pytest.mark.asyncio
    async def test_generate_handles_auth_error(self, mocker):
        """generate() translates authentication errors."""
        from openai import AuthenticationError
        from unittest.mock import MagicMock
        
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        # Create a proper mock response for the error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid API key"
        
        error = AuthenticationError("Invalid API key", response=mock_response, body={})
        mock_client.chat.completions.create = AsyncMock(side_effect=error)
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(RuntimeError, match="authentication"):
            await gateway.generate(messages)
    
    @pytest.mark.asyncio
    async def test_generate_handles_quota_error(self, mocker):
        """generate() handles quota exceeded errors."""
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("insufficient quota")
        )
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(RuntimeError, match="quota"):
            await gateway.generate(messages)
    
    @pytest.mark.asyncio
    async def test_generate_handles_generic_error(self, mocker):
        """generate() wraps unknown errors."""
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Some random error")
        )
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        messages = [Message(role=MessageRole.USER, content="test")]
        
        with pytest.raises(RuntimeError, match="API error"):
            await gateway.generate(messages)


# ============================================================================
# Close Method Tests
# ============================================================================

class TestOpenAIGatewayClose:
    """Test cleanup and resource management."""
    
    @pytest.mark.asyncio
    async def test_close_calls_client_close(self, mocker):
        """close() calls client.close()."""
        mock_client = AsyncMock()
        mocker.patch("adapters.llm.adapter_openai.AsyncOpenAI", return_value=mock_client)
        
        gateway = OpenAIGateway(api_key="sk-test-key")
        
        await gateway.close()
        
        mock_client.close.assert_called_once()
