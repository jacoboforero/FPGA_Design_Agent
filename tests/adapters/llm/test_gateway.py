"""
Unit tests for adapters/llm/gateway.py

Tests the base gateway abstractions:
- Message, ModelResponse, GenerationConfig classes
- LLMGateway abstract base class
- quick_generate utility function
"""

import pytest
from datetime import datetime, timezone
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
    LLMGateway,
    quick_generate,
    utc_now,
)


# ============================================================================
# MessageRole Tests
# ============================================================================

class TestMessageRole:
    """Test MessageRole enum."""
    
    def test_message_role_values(self):
        """Verify MessageRole enum has expected values."""
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
    
    def test_message_role_string_conversion(self):
        """Test converting MessageRole to string."""
        role = MessageRole.USER
        assert str(role.value) == "user"


# ============================================================================
# Message Tests
# ============================================================================

class TestMessage:
    """Test Message class."""
    
    def test_message_creation(self):
        """Create a valid message."""
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.attachments == []
    
    def test_message_with_attachments(self):
        """Create message with attachments."""
        attachments = [
            {"filename": "test.v", "content": "module test();endmodule"},
            {"filename": "spec.md", "content": "# Specification"},
        ]
        msg = Message(
            role=MessageRole.USER,
            content="Analyze this:",
            attachments=attachments
        )
        assert len(msg.attachments) == 2
        assert msg.attachments[0]["filename"] == "test.v"
    
    def test_message_serialize_deserialize(self):
        """Test Pydantic serialization of Message."""
        msg = Message(
            role=MessageRole.SYSTEM,
            content="You are helpful",
            attachments=[{"data": "test"}]
        )
        # Pydantic model_dump
        dumped = msg.model_dump()
        assert dumped["role"] == "system"
        assert dumped["content"] == "You are helpful"
        
        # Reconstruct
        reconstructed = Message(**dumped)
        assert reconstructed.role == MessageRole.SYSTEM
    
    def test_message_empty_content_allowed(self):
        """Empty content should be allowed."""
        msg = Message(role=MessageRole.USER, content="")
        assert msg.content == ""
    
    def test_message_very_long_content(self):
        """Test message with large content."""
        long_content = "x" * 100000
        msg = Message(role=MessageRole.USER, content=long_content)
        assert len(msg.content) == 100000


# ============================================================================
# GenerationConfig Tests
# ============================================================================

class TestGenerationConfig:
    """Test GenerationConfig class."""
    
    def test_default_config(self):
        """Default config has sensible values."""
        config = GenerationConfig()
        assert config.max_tokens is None
        assert config.temperature is None
        assert config.top_p is None
        assert config.top_k is None
        assert config.stop_sequences == []
        assert config.provider_specific == {}
    
    def test_config_with_parameters(self):
        """Config with all parameters set."""
        config = GenerationConfig(
            max_tokens=500,
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            stop_sequences=["```", "EOF"],
            provider_specific={"custom": "value"},
        )
        assert config.max_tokens == 500
        assert config.temperature == 0.7
        assert config.top_p == 0.9
        assert config.top_k == 40
        assert config.stop_sequences == ["```", "EOF"]
        assert config.provider_specific["custom"] == "value"
    
    def test_config_partial_updates(self):
        """Create config with some parameters, leave others default."""
        config = GenerationConfig(
            temperature=0.5,
            max_tokens=1000,
        )
        assert config.temperature == 0.5
        assert config.max_tokens == 1000
        assert config.top_p is None
        assert config.stop_sequences == []
    
    def test_config_edge_case_values(self):
        """Test edge case values for config."""
        config = GenerationConfig(
            max_tokens=1,  # Minimum
            temperature=0.0,  # Absolute zero temperature
            top_p=0.0,  # Minimum sampling
        )
        assert config.max_tokens == 1
        assert config.temperature == 0.0
        assert config.top_p == 0.0
    
    def test_config_serialize_deserialize(self):
        """Test Pydantic serialization of GenerationConfig."""
        original = GenerationConfig(
            max_tokens=200,
            temperature=0.8,
            stop_sequences=["STOP"],
        )
        dumped = original.model_dump()
        reconstructed = GenerationConfig(**dumped)
        
        assert reconstructed.max_tokens == 200
        assert reconstructed.temperature == 0.8
        assert reconstructed.stop_sequences == ["STOP"]


# ============================================================================
# ModelResponse Tests
# ============================================================================

class TestModelResponse:
    """Test ModelResponse class."""
    
    def test_response_creation(self):
        """Create a valid response."""
        response = ModelResponse(
            content="Hello, world!",
            input_tokens=5,
            output_tokens=3,
            total_tokens=8,
            model_name="gpt-4o",
            provider="openai",
        )
        assert response.content == "Hello, world!"
        assert response.input_tokens == 5
        assert response.output_tokens == 3
        assert response.total_tokens == 8
    
    def test_response_with_optional_fields(self):
        """Response with all optional fields."""
        response = ModelResponse(
            content="code",
            input_tokens=100,
            output_tokens=200,
            total_tokens=300,
            estimated_cost_usd=0.025,
            model_name="gpt-5",
            provider="openai",
            finish_reason="length",
            raw_response={"id": "12345"},
        )
        assert response.estimated_cost_usd == 0.025
        assert response.finish_reason == "length"
        assert response.raw_response["id"] == "12345"
    
    def test_response_timestamp_auto_generated(self):
        """Verify timestamp is auto-generated."""
        response = ModelResponse(
            content="test",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            model_name="test-model",
            provider="test",
        )
        assert response.timestamp is not None
        assert isinstance(response.timestamp, datetime)
        # Should be recent (within last minute)
        now = datetime.now(timezone.utc)
        diff = (now - response.timestamp).total_seconds()
        assert 0 <= diff < 60
    
    def test_response_token_accounting(self):
        """Verify token counts are tracked correctly."""
        response = ModelResponse(
            content="x" * 100,
            input_tokens=50,
            output_tokens=75,
            total_tokens=125,
            model_name="test",
            provider="test",
        )
        assert response.total_tokens == response.input_tokens + response.output_tokens
    
    def test_response_zero_tokens(self):
        """Edge case: zero tokens (shouldn't happen in practice, but should be valid)."""
        response = ModelResponse(
            content="",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            model_name="test",
            provider="test",
        )
        assert response.total_tokens == 0
    
    def test_response_large_token_counts(self):
        """Test response with large token counts."""
        response = ModelResponse(
            content="x" * 10000,
            input_tokens=100000,
            output_tokens=50000,
            total_tokens=150000,
            model_name="test-long",
            provider="test",
        )
        assert response.total_tokens == 150000
    
    def test_response_serialize_deserialize(self):
        """Test Pydantic serialization of ModelResponse."""
        original = ModelResponse(
            content="result",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            model_name="test-model",
            provider="test-provider",
            finish_reason="stop",
            estimated_cost_usd=0.001,
        )
        dumped = original.model_dump()
        reconstructed = ModelResponse(**dumped)
        
        assert reconstructed.content == "result"
        assert reconstructed.input_tokens == 10
        assert reconstructed.provider == "test-provider"


# ============================================================================
# Utility Function Tests
# ============================================================================

class TestUtcNow:
    """Test utc_now utility."""
    
    def test_utc_now_returns_datetime(self):
        """utc_now returns a datetime object."""
        now = utc_now()
        assert isinstance(now, datetime)
    
    def test_utc_now_is_utc(self):
        """utc_now returns UTC time."""
        now = utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc
    
    def test_utc_now_recent(self):
        """utc_now returns current time."""
        before = datetime.now(timezone.utc)
        now = utc_now()
        after = datetime.now(timezone.utc)
        
        assert before <= now <= after


# ============================================================================
# Abstract Base Class Tests
# ============================================================================

class TestLLMGatewayAbstract:
    """Test LLMGateway abstract base class."""
    
    def test_cannot_instantiate_abstract_class(self):
        """LLMGateway cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LLMGateway()
    
    def test_concrete_subclass_requires_implementation(self):
        """A subclass must implement abstract methods."""
        # This should work - implementing all abstract methods
        class ConcreteGateway(LLMGateway):
            async def generate(self, messages, config=None):
                return ModelResponse(
                    content="test",
                    input_tokens=1,
                    output_tokens=1,
                    total_tokens=2,
                    model_name="test",
                    provider="test"
                )
            
            @property
            def model_name(self):
                return "test-model"
            
            @property
            def provider(self):
                return "test"
            
            @property
            def supports_files(self):
                return False
        
        # Should instantiate without error
        gateway = ConcreteGateway()
        assert gateway.model_name == "test-model"
        assert gateway.provider == "test"
    
    def test_validate_config_default_implementation(self):
        """Default validate_config just returns the config."""
        class SimpleGateway(LLMGateway):
            async def generate(self, messages, config=None):
                pass
            
            @property
            def model_name(self):
                return "simple"
            
            @property
            def provider(self):
                return "simple"
            
            @property
            def supports_files(self):
                return False
        
        gateway = SimpleGateway()
        config = GenerationConfig(temperature=0.5)
        validated = gateway.validate_config(config)
        
        assert validated.temperature == 0.5
    
    def test_estimate_cost_default_implementation(self):
        """Default estimate_cost returns 0.0."""
        class SimpleGateway(LLMGateway):
            async def generate(self, messages, config=None):
                pass
            
            @property
            def model_name(self):
                return "simple"
            
            @property
            def provider(self):
                return "simple"
            
            @property
            def supports_files(self):
                return False
        
        gateway = SimpleGateway()
        response = ModelResponse(
            content="test",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            model_name="simple",
            provider="simple",
        )
        cost = gateway.estimate_cost(response)
        assert cost == 0.0


# ============================================================================
# quick_generate Function Tests
# ============================================================================

class TestQuickGenerate:
    """Test the quick_generate convenience function."""
    
    @pytest.mark.asyncio
    async def test_quick_generate_user_prompt_only(self, mocker):
        """quick_generate with just a user prompt."""
        mock_response = ModelResponse(
            content="response",
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            model_name="test",
            provider="test",
        )
        
        mock_gateway = mocker.MagicMock()
        mock_gateway.generate = mocker.AsyncMock(return_value=mock_response)
        
        result = await quick_generate(mock_gateway, "Hello")
        
        # Should have been called with one message
        mock_gateway.generate.assert_called_once()
        call_args = mock_gateway.generate.call_args
        messages = call_args[1]["messages"]
        
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER
        assert messages[0].content == "Hello"
    
    @pytest.mark.asyncio
    async def test_quick_generate_with_system_prompt(self, mocker):
        """quick_generate with system and user prompts."""
        mock_response = ModelResponse(
            content="response",
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            model_name="test",
            provider="test",
        )
        
        mock_gateway = mocker.MagicMock()
        mock_gateway.generate = mocker.AsyncMock(return_value=mock_response)
        
        result = await quick_generate(
            mock_gateway,
            "Generate code",
            system_prompt="You are a code generator"
        )
        
        call_args = mock_gateway.generate.call_args
        messages = call_args[1]["messages"]
        
        assert len(messages) == 2
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[0].content == "You are a code generator"
        assert messages[1].role == MessageRole.USER
        assert messages[1].content == "Generate code"
    
    @pytest.mark.asyncio
    async def test_quick_generate_with_config(self, mocker):
        """quick_generate passes through generation config."""
        mock_response = ModelResponse(
            content="response",
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            model_name="test",
            provider="test",
        )
        
        mock_gateway = mocker.MagicMock()
        mock_gateway.generate = mocker.AsyncMock(return_value=mock_response)
        
        config = GenerationConfig(temperature=0.3, max_tokens=200)
        
        result = await quick_generate(
            mock_gateway,
            "Prompt",
            config=config
        )
        
        call_args = mock_gateway.generate.call_args
        passed_config = call_args[1]["config"]
        
        assert passed_config.temperature == 0.3
        assert passed_config.max_tokens == 200
    
    @pytest.mark.asyncio
    async def test_quick_generate_returns_response(self, mocker):
        """quick_generate returns the gateway response."""
        expected_response = ModelResponse(
            content="generated content",
            input_tokens=42,
            output_tokens=84,
            total_tokens=126,
            model_name="gpt-4o",
            provider="openai",
        )
        
        mock_gateway = mocker.MagicMock()
        mock_gateway.generate = mocker.AsyncMock(return_value=expected_response)
        
        result = await quick_generate(mock_gateway, "Test")
        
        assert result == expected_response
        assert result.content == "generated content"
