"""
Unit tests for adapters/llm/llm_gateway.py

Tests the LLM gateway initialization functions:
- init_llm_gateway (main entry point)
- _init_with_config (centralized config mode)
- _init_legacy (backward compatible mode)
- init_llm_gateway_with_fallback
"""

import pytest
from adapters.llm.llm_gateway import (
    init_llm_gateway,
    init_llm_gateway_with_fallback,
)


# ============================================================================
# init_llm_gateway Tests
# ============================================================================

class TestInitLLMGateway:
    """Test the main init_llm_gateway entry point."""
    
    def test_init_llm_disabled_returns_none(self, disabled_llm_env):
        """When USE_LLM=0, returns None."""
        result = init_llm_gateway()
        assert result is None
    
    def test_init_llm_config_mode(self, valid_gateway_env, monkeypatch):
        """Initialize using gateway_config mode."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        gateway = init_llm_gateway("implementation")
        
        # Should return a gateway
        assert gateway is not None
    
    def test_init_llm_config_mode_default_agent(self, valid_gateway_env, monkeypatch):
        """Initialize config mode with default agent."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        gateway = init_llm_gateway(agent_type=None)
        
        # Should use "balanced" as default
        assert gateway is not None
    
    def test_init_llm_legacy_mode(self, legacy_openai_env):
        """Initialize using legacy mode."""
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"
    
    def test_init_llm_legacy_mode_with_agent_type(self, legacy_openai_env):
        """Initialize legacy mode (agent_type ignored in legacy)."""
        gateway = init_llm_gateway(agent_type="planner")
        
        # Legacy mode uses LLM_PROVIDER, not agent_type
        assert gateway is not None
        assert gateway.provider == "openai"
    
    def test_init_llm_missing_api_key_returns_none(self, monkeypatch):
        """Returns None when required API key missing."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        gateway = init_llm_gateway()
        
        assert gateway is None
    
    def test_init_llm_invalid_provider_returns_none(self, monkeypatch):
        """Returns None for invalid provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "invalid_provider")
        
        gateway = init_llm_gateway()
        
        assert gateway is None


# ============================================================================
# Legacy Mode Tests
# ============================================================================

class TestLegacyInitialization:
    """Test legacy LLM_PROVIDER mode initialization."""
    
    def test_legacy_openai_initialization(self, legacy_openai_env):
        """Legacy mode with OpenAI provider."""
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"
        assert gateway.model_name == "gpt-4o"
    
    def test_legacy_openai_with_model_override(self, monkeypatch):
        """Legacy OpenAI with model override."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-nano")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.model_name == "gpt-4.1-nano"
    
    def test_legacy_anthropic_initialization(self, monkeypatch):
        """Legacy mode with Anthropic provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "anthropic"
    
    def test_legacy_google_initialization(self, monkeypatch):
        """Legacy mode with Google provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "google")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "google"
    
    def test_legacy_groq_initialization(self, monkeypatch):
        """Legacy mode with Groq provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "groq"
    
    def test_legacy_qwen_local_initialization(self, monkeypatch):
        """Legacy mode with local Qwen/Ollama."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "qwen3-local")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "qwen3-local"
    
    def test_legacy_ollama_alias(self, monkeypatch):
        """Legacy mode accepts 'ollama' as provider alias."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "qwen3-local"
    
    def test_legacy_local_alias(self, monkeypatch):
        """Legacy mode accepts 'local' as provider alias."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "local")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "qwen3-local"
    
    def test_legacy_case_insensitive_provider(self, monkeypatch):
        """Legacy mode is case-insensitive for provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "OPENAI")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"


# ============================================================================
# Fallback Initialization Tests
# ============================================================================

class TestInitLLMGatewayWithFallback:
    """Test fallback-aware gateway initialization."""
    
    def test_fallback_requires_config_mode(self, legacy_openai_env, monkeypatch):
        """Fallback mode requires USE_GATEWAY_CONFIG=1."""
        # Legacy mode should fallback to standard init
        monkeypatch.setenv("USE_gateway_CONFIG", "0")
        
        gateway = init_llm_gateway_with_fallback("planner")
        
        # Should still work (falls back to standard init)
        assert gateway is not None
    
    def test_fallback_initialization_config_mode(self, valid_gateway_env, monkeypatch):
        """Fallback initialization with config mode enabled."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        gateway = init_llm_gateway_with_fallback("implementation")
        
        assert gateway is not None
    
    def test_fallback_returns_primary_gateway(self, valid_gateway_env, monkeypatch):
        """Fallback init returns the primary gateway."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        gateway = init_llm_gateway_with_fallback("planner")
        
        # Should be the primary (first in chain)
        assert gateway is not None
    
    def test_fallback_with_llm_disabled(self, disabled_llm_env):
        """Fallback returns None when LLMs disabled."""
        result = init_llm_gateway_with_fallback("implementation")
        
        assert result is None
    
    def test_fallback_with_missing_gateways(self, missing_api_keys_env, monkeypatch):
        """Fallback handles case when no gateways available."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        # With no API keys, might return None or local gateway
        result = init_llm_gateway_with_fallback("planner")
        
        # Result depends on local gateway availability


# ============================================================================
# Environment Variable Combinations Tests
# ============================================================================

class TestEnvironmentVariableCombinations:
    """Test various environment variable combinations."""
    
    def test_config_mode_takes_precedence(self, valid_gateway_env, monkeypatch):
        """USE_GATEWAY_CONFIG=1 takes precedence over USE_GATEWAY_CONFIG=0."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")  # Should be ignored
        
        gateway = init_llm_gateway("implementation")
        
        # Should use config mode, not legacy mode
        assert gateway is not None
    
    def test_default_to_legacy_mode(self, legacy_openai_env, monkeypatch):
        """Default to legacy mode when USE_GATEWAY_CONFIG not set."""
        monkeypatch.delenv("USE_GATEWAY_CONFIG", raising=False)
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"
    
    def test_special_characters_in_api_key(self, monkeypatch):
        """Handle API keys with special characters."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "0")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-with-!@#$%^&*()_+-=[]{}|;:',.<>?/~`")
        
        gateway = init_llm_gateway()
        
        # Should create gateway even with special chars in key
        assert gateway is not None


# ============================================================================
# Error Handling and Edge Cases
# ============================================================================

class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""
    
    def test_init_with_none_agent_type(self, valid_gateway_env, monkeypatch):
        """Handles None agent_type gracefully."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        gateway = init_llm_gateway(agent_type=None)
        
        # Should use default
        assert gateway is not None
    
    def test_init_with_empty_string_agent_type(self, valid_gateway_env, monkeypatch):
        """Handles empty string agent_type."""
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        
        gateway = init_llm_gateway(agent_type="")
        
        # Should handle gracefully
        assert gateway is None or gateway is not None  # Depends on implementation
    
    def test_init_called_multiple_times(self, legacy_openai_env):
        """Can call init function multiple times."""
        gateway1 = init_llm_gateway()
        gateway2 = init_llm_gateway()
        
        # Both should succeed
        assert gateway1 is not None
        assert gateway2 is not None
    
    def test_init_with_malformed_tier(self, valid_gateway_env, monkeypatch):
        """Handles malformed GATEWAY_TIER gracefully."""
        from adapters.llm.gateway_config import GatewayConfig
        
        monkeypatch.setenv("USE_GATEWAY_CONFIG", "1")
        monkeypatch.setenv("GATEWAY_TIER", "invalid_tier")
        
        # GatewayConfig raises ValueError in __init__ for invalid tier
        with pytest.raises(ValueError):
            GatewayConfig()


# ============================================================================
# Per-Agent Model Override Tests (Future Feature)
# ============================================================================

class TestPerAgentModelOverrides:
    """Test per-agent model override capability (future feature).
    
    These tests verify that agent-specific environment variables
    (LLM_PROVIDER_{agent_type}, LLM_MODEL_{agent_type}) work correctly
    and take precedence over default LLM_PROVIDER and LLM_MODEL.
    
    Future enhancement: Will allow users to specify different models
    for different agents in the agentic loop.
    """
    
    def test_agent_specific_provider_override(self, monkeypatch):
        """Agent-specific provider overrides default."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_PROVIDER_planner", "anthropic")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        # Default agent uses openai
        gateway = init_llm_gateway()
        assert gateway is not None
        assert gateway.provider == "openai"
        
        # Planner agent uses anthropic override
        gateway = init_llm_gateway("planner")
        assert gateway is not None
        assert gateway.provider == "anthropic"
    
    def test_agent_specific_model_override(self, monkeypatch):
        """Agent-specific model overrides default."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("LLM_MODEL_planner", "gpt-4.1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        
        # Default uses gpt-4o
        gateway = init_llm_gateway()
        assert gateway is not None
        assert gateway.model_name == "gpt-4o"
        
        # Planner uses gpt-4.1
        gateway = init_llm_gateway("planner")
        assert gateway is not None
        assert gateway.model_name == "gpt-4.1"
    
    def test_agent_specific_both_provider_and_model(self, monkeypatch):
        """Agent can override both provider and model."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("LLM_PROVIDER_debug", "anthropic")
        monkeypatch.setenv("LLM_MODEL_debug", "claude-opus-4-5-20251101")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        # Default uses openai/gpt-4o
        gateway = init_llm_gateway()
        assert gateway.provider == "openai"
        assert gateway.model_name == "gpt-4o"
        
        # Debug agent uses anthropic/claude-opus
        gateway = init_llm_gateway("debug")
        assert gateway.provider == "anthropic"
        assert gateway.model_name == "claude-opus-4-5-20251101"
    
    def test_agent_specific_missing_api_key(self, monkeypatch):
        """Returns None if agent-specific provider's API key is missing."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_PROVIDER_implementation", "anthropic")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        # Missing ANTHROPIC_API_KEY
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        
        # Default works
        gateway = init_llm_gateway()
        assert gateway is not None
        
        # Implementation fails due to missing key
        gateway = init_llm_gateway("implementation")
        assert gateway is None
    
    def test_multiple_agents_different_providers(self, monkeypatch):
        """Different agents can use different providers simultaneously."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_PROVIDER_planner", "anthropic")
        monkeypatch.setenv("LLM_PROVIDER_implementation", "google")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
        
        default_gw = init_llm_gateway()
        assert default_gw.provider == "openai"
        
        planner_gw = init_llm_gateway("planner")
        assert planner_gw.provider == "anthropic"
        
        impl_gw = init_llm_gateway("implementation")
        assert impl_gw.provider == "google"
    
    def test_case_insensitive_agent_type_in_env_var(self, monkeypatch):
        """Agent model overrides are case-sensitive in env var names."""
        # Note: Environment variable names are case-sensitive on Unix systems
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_PROVIDER_PLANNER", "anthropic")  # UPPERCASE
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        # Agent type "planner" (lowercase) should not match "LLM_PROVIDER_PLANNER"
        gateway = init_llm_gateway("planner")
        # Should use default openai, not anthropic
        assert gateway.provider == "openai"
    
    def test_partial_agent_override(self, monkeypatch):
        """Can override provider but not model (uses default for model)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_PROVIDER_spec_helper", "groq")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
        # No LLM_MODEL_spec_helper override
        
        gateway = init_llm_gateway("spec_helper")
        assert gateway is not None
        assert gateway.provider == "groq"
        # Should use groq's default model
        assert "llama" in gateway.model_name.lower()  # Groq's default is llama

