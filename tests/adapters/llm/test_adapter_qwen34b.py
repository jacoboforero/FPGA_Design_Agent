"""
Unit tests for adapters/llm/adapter_qwen34b.py

Tests the Qwen3:4b local gateway implementation (via Ollama):
- Qwen34BLocalGateway initialization
- Ollama API call handling
- Message format conversion
- Response parsing
- Configuration validation
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from adapters.llm.adapter_qwen34b import Qwen34BLocalGateway
from adapters.llm.gateway import (
    Message,
    MessageRole,
    GenerationConfig,
    ModelResponse,
)


# ============================================================================
# Qwen34BLocalGateway Initialization Tests
# ============================================================================

class TestQwen34BLocalGatewayInit:
    """Test Qwen34BLocalGateway initialization."""
    
    def test_init_with_defaults(self):
        """Initialize with defaults (localhost Ollama)."""
        gateway = Qwen34BLocalGateway()
        
        assert gateway._model == "qwen3:4b"
        assert gateway._base_url == "http://localhost:11434"
        assert gateway._timeout == 300.0
    
    def test_init_with_custom_base_url(self):
        """Initialize with custom Ollama server URL."""
        gateway = Qwen34BLocalGateway(
            ollama_base_url="http://192.168.1.100:11434"
        )
        
        assert gateway._base_url == "http://192.168.1.100:11434"
    
    def test_init_strips_trailing_slash(self):
        """Initialize strips trailing slash from base URL."""
        gateway = Qwen34BLocalGateway(
            ollama_base_url="http://localhost:11434/"
        )
        
        assert gateway._base_url == "http://localhost:11434"
    
    def test_init_with_custom_timeout(self):
        """Initialize with custom timeout."""
        gateway = Qwen34BLocalGateway(timeout=600.0)
        
        assert gateway._timeout == 600.0
    
    def test_init_constructs_api_url(self):
        """Initialization constructs API endpoint URL."""
        gateway = Qwen34BLocalGateway()
        
        assert gateway._api_url == "http://localhost:11434/api/chat"


# ============================================================================
# Properties Tests
# ============================================================================

class TestQwen34BLocalGatewayProperties:
    """Test Qwen34BLocalGateway properties."""
    
    def test_model_name_property(self):
        """model_name property returns qwen3:4b."""
        gateway = Qwen34BLocalGateway()
        
        assert gateway.model_name == "qwen3:4b"
    
    def test_provider_property(self):
        """provider property returns 'qwen3-local'."""
        gateway = Qwen34BLocalGateway()
        
        assert gateway.provider == "qwen3-local"
    
    def test_supports_files(self):
        """supports_files is True for Qwen3:4b (supports text files)."""
        gateway = Qwen34BLocalGateway()
        
        assert gateway.supports_files is True


# ============================================================================
# Message Conversion Tests
# ============================================================================

class TestQwen34BMessageConversion:
    """Test Qwen3:4b message format conversion."""
    
    def test_convert_simple_user_message(self):
        """Convert simple user message to Ollama format."""
        gateway = Qwen34BLocalGateway()
        
        message = Message(role=MessageRole.USER, content="Hello")
        converted = gateway._convert_messages([message])
        
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"
    
    def test_convert_system_message(self):
        """Convert system message."""
        gateway = Qwen34BLocalGateway()
        
        message = Message(role=MessageRole.SYSTEM, content="You are helpful")
        converted = gateway._convert_messages([message])
        
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are helpful"
    
    def test_convert_multi_turn(self):
        """Convert multi-turn conversation."""
        gateway = Qwen34BLocalGateway()
        
        messages = [
            Message(role=MessageRole.USER, content="Hi"),
            Message(role=MessageRole.ASSISTANT, content="Hey"),
            Message(role=MessageRole.USER, content="I need coding help"),
        ]
        
        converted = gateway._convert_messages(messages)
        
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "assistant"
        assert converted[2]["role"] == "user"
    
    def test_convert_empty_message_list(self):
        """Convert empty message list."""
        gateway = Qwen34BLocalGateway()
        
        # Qwen34B _convert_messages returns a List, not a tuple
        converted = gateway._convert_messages([])
        
        assert converted == []


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestQwen34BConfigValidation:
    """Test Qwen3:4b-specific config validation."""
    
    def test_validate_temperature_in_range(self):
        """Valid temperature [0, 2] passes."""
        gateway = Qwen34BLocalGateway()
        
        for temp in [0.0, 0.5, 1.0, 2.0]:
            config = GenerationConfig(temperature=temp)
            validated = gateway.validate_config(config)
            assert validated.temperature == temp
    
    def test_validate_top_p_in_range(self):
        """Valid top_p [0, 1] passes."""
        gateway = Qwen34BLocalGateway()
        
        config = GenerationConfig(top_p=0.9)
        validated = gateway.validate_config(config)
        assert validated.top_p == 0.9
    
    def test_validate_top_k_supported(self):
        """top_k is supported by Ollama."""
        gateway = Qwen34BLocalGateway()
        
        config = GenerationConfig(top_k=40)
        validated = gateway.validate_config(config)
        assert validated.top_k == 40


# ============================================================================
# Response Conversion Tests
# ============================================================================

class TestQwen34BResponseConversion:
    """Test Qwen3:4b response parsing and conversion."""
    
    def test_convert_successful_response(self):
        """Convert successful Ollama API response."""
        gateway = Qwen34BLocalGateway()
        
        # Mock response from Ollama
        ollama_response = {
            "model": "qwen3:4b",
            "created_at": "2025-02-08T00:00:00.000000Z",
            "message": {
                "role": "assistant",
                "content": "Here's a Verilog module...",
            },
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
        assert converted.provider == "qwen3-local"
    
    def test_convert_response_with_content(self):
        """Convert response with content."""
        gateway = Qwen34BLocalGateway()
        
        ollama_response = {
            "model": "qwen3:4b",
            "message": {"role": "assistant", "content": "Generated code"},
            "done": True,
            "prompt_eval_count": 50,
            "eval_count": 100,
        }
        
        converted = gateway._convert_response(ollama_response)
        
        assert converted.content == "Generated code"
        assert converted.input_tokens == 50
        assert converted.output_tokens == 100


# ============================================================================
# Generate Tests
# ============================================================================

class TestQwen34BGenerate:
    """Test Qwen3:4b generate method."""
    
    @pytest.mark.asyncio
    async def test_generate_with_config(self):
        """Generate response with custom config."""
        gateway = Qwen34BLocalGateway()
        
        with patch("adapters.llm.adapter_qwen34b.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "Generated code"},
                "done": True,
                "prompt_eval_count": 50,
                "eval_count": 100,
            })
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
        """Generate handles timeout errors."""
        gateway = Qwen34BLocalGateway(timeout=1.0)
        
        with patch("adapters.llm.adapter_qwen34b.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=Exception("Request timed out")
            )
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            
            messages = [Message(role=MessageRole.USER, content="test")]
            
            with pytest.raises(RuntimeError, match="timed out"):
                await gateway.generate(messages)
    
    @pytest.mark.asyncio
    async def test_generate_handles_http_errors(self):
        """Generate handles HTTP errors."""
        gateway = Qwen34BLocalGateway()
        
        with patch("adapters.llm.adapter_qwen34b.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock(
                side_effect=Exception("404 Not Found")
            )
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            
            messages = [Message(role=MessageRole.USER, content="test")]
            
            with pytest.raises(RuntimeError):
                await gateway.generate(messages)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestQwen34BErrorHandling:
    """Test Qwen3:4b error handling."""
    
    def test_custom_ollama_url(self):
        """Can connect to custom Ollama instance."""
        gateway = Qwen34BLocalGateway(
            ollama_base_url="http://ollama.example.com:11434"
        )
        
        assert gateway._api_url == "http://ollama.example.com:11434/api/chat"
    
    @pytest.mark.asyncio
    async def test_generate_with_provider_specific_options(self):
        """Generate passes provider-specific options to Ollama."""
        gateway = Qwen34BLocalGateway()
        
        with patch("adapters.llm.adapter_qwen34b.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json = MagicMock(return_value={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "result"},
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 20,
            })
            mock_response.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            
            messages = [Message(role=MessageRole.USER, content="test")]
            config = GenerationConfig(
                temperature=0.7,
                provider_specific={"num_keep": 5, "penalize_newline": True}
            )
            
            result = await gateway.generate(messages, config)
            
            # Verify the call was made
            assert mock_client.post.called


# ============================================================================
# Integration Tests
# ============================================================================

class TestQwen34BIntegration:
    """Integration tests for Qwen3:4b gateway."""
    
    def test_api_url_construction(self):
        """Verify API URL is correctly constructed."""
        test_cases = [
            ("http://localhost:11434", "http://localhost:11434/api/chat"),
            ("http://localhost:11434/", "http://localhost:11434/api/chat"),
            ("http://192.168.1.1:11434", "http://192.168.1.1:11434/api/chat"),
            ("https://ollama.example.com", "https://ollama.example.com/api/chat"),
        ]
        
        for base_url, expected_api_url in test_cases:
            gateway = Qwen34BLocalGateway(ollama_base_url=base_url)
            assert gateway._api_url == expected_api_url
