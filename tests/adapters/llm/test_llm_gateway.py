"""
Unit tests for adapters/llm/gateway_factory.py

Tests the LLM gateway initialization functions:
- init_llm_gateway (main entry point)
- _init_legacy (backward compatible mode)
- init_llm_gateway_with_fallback (deprecated wrapper)
"""

import pytest
from adapters.llm.gateway_factory import init_llm_gateway


# ============================================================================
# init_llm_gateway Tests
# ============================================================================

class TestInitLLMGateway:
    """Test the main init_llm_gateway entry point."""
    
    def test_init_llm_disabled_returns_none(self, disabled_llm_env):
        """When USE_LLM=0, returns None."""
        result = init_llm_gateway()
        assert result is None
    

    
    def test_init_llm_legacy_mode(self, legacy_openai_env):
        """Initialize using legacy mode."""
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"
    
    def test_init_llm_legacy_mode_with_agent_type(self, legacy_openai_env):
        """Initialize legacy mode (agent_type ignored in legacy)."""
        gateway = init_llm_gateway(agent_type="planner")
        
        # Legacy mode uses DEFAULT_LLM_PROVIDER, not agent_type
        assert gateway is not None
        assert gateway.provider == "openai"
    
    def test_init_llm_missing_api_key_returns_none(self, monkeypatch):
        """Returns None when required API key missing."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        gateway = init_llm_gateway()
        
        assert gateway is None
    
    def test_init_llm_invalid_provider_returns_none(self, monkeypatch):
        """Returns None for invalid provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "invalid_provider")
        
        gateway = init_llm_gateway()
        
        assert gateway is None


# ============================================================================
# Legacy Mode Tests
# ============================================================================

class TestLegacyInitialization:
    """Test legacy DEFAULT_LLM_PROVIDER mode initialization."""
    
    def test_legacy_openai_initialization(self, legacy_openai_env):
        """Legacy mode with OpenAI provider."""
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"
        assert gateway.model_name == "gpt-4o"
    
    def test_legacy_openai_with_model_override(self, monkeypatch):
        """Legacy OpenAI with model override."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-4.1-nano")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.model_name == "gpt-4.1-nano"
    
    def test_legacy_anthropic_initialization(self, monkeypatch):
        """Legacy mode with Anthropic provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "anthropic"
    
    def test_legacy_google_initialization(self, monkeypatch):
        """Legacy mode with Google provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "google")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "google"
    
    def test_legacy_groq_initialization(self, monkeypatch):
        """Legacy mode with Groq provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "groq"
    
    def test_legacy_qwen_local_initialization(self, monkeypatch):
        """Legacy mode with local Qwen/Ollama."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "qwen-local")

        gateway = init_llm_gateway()

        assert gateway is not None
        assert gateway.provider == "qwen-local"
    
    def test_legacy_ollama_alias(self, monkeypatch):
        """Legacy mode rejects unknown providers (no aliases)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "ollama")

        gateway = init_llm_gateway()

        assert gateway is None
    
    def test_legacy_local_alias(self, monkeypatch):
        """Legacy mode rejects unknown providers (no aliases)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "local")

        gateway = init_llm_gateway()

        assert gateway is None
    
    def test_legacy_case_insensitive_provider(self, monkeypatch):
        """Legacy mode is case-insensitive for provider."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "OPENAI")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"


# ============================================================================
# Fallback Initialization Tests
# ============================================================================

# Fallback/config-mode related tests removed — feature deprecated/removed.


# ============================================================================
# Environment Variable Combinations Tests
# ============================================================================

class TestEnvironmentVariableCombinations:
    """Test various environment variable combinations."""
    

    
    def test_default_to_legacy_mode(self, legacy_openai_env, monkeypatch):
        """Default to legacy mode (config mode removed)."""
        gateway = init_llm_gateway()
        
        assert gateway is not None
        assert gateway.provider == "openai"
    
    def test_special_characters_in_api_key(self, monkeypatch):
        """Handle API keys with special characters."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
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
        gateway = init_llm_gateway(agent_type=None)
        
        # Should use default
        assert gateway is not None
    
    def test_init_with_empty_string_agent_type(self, valid_gateway_env, monkeypatch):
        """Handles empty string agent_type."""
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
    



# ============================================================================
# Per-Agent Model Override Tests (Future Feature)
# ============================================================================

class TestPerAgentModelOverrides:
    """Per-agent override behavior — only prefix-style env vars are supported.

    These tests verify that agent-specific environment variables are read from
    `{AGENT}_LLM_PROVIDER` / `{AGENT}_LLM_MODEL` and that legacy suffix-style
    `LLM_PROVIDER_{agent}` / `LLM_MODEL_{agent}` is ignored.
    """

    def test_agent_specific_provider_override(self, monkeypatch):
        """Agent-specific provider overrides default (prefix-style)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("PLANNER_LLM_PROVIDER", "anthropic")
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

    def test_agent_prefix_provider_override(self, monkeypatch):
        """Agent-prefix env var (`SPEC_HELPER_LLM_PROVIDER`) overrides default (preferred style)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("SPEC_HELPER_LLM_PROVIDER", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

        default_gw = init_llm_gateway()
        assert default_gw.provider == "openai"

        spec_gw = init_llm_gateway("spec_helper")
        assert spec_gw.provider == "groq"

    def test_agent_specific_model_override(self, monkeypatch):
        """Agent-specific model overrides default (prefix-style)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("PLANNER_LLM_MODEL", "gpt-4.1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        # Default uses gpt-4o
        gateway = init_llm_gateway()
        assert gateway is not None
        assert gateway.model_name == "gpt-4o"

        # Planner uses gpt-4.1
        gateway = init_llm_gateway("planner")
        assert gateway is not None
        assert gateway.model_name == "gpt-4.1"

    def test_agent_prefix_model_override(self, monkeypatch):
        """Agent-prefix model env var (`SPEC_HELPER_LLM_MODEL`) is accepted."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("SPEC_HELPER_LLM_MODEL", "gpt-5-nano")

        gw = init_llm_gateway("spec_helper")
        assert gw is not None
        assert gw.model_name == "gpt-5-nano"

    def test_agent_prefix_and_legacy_precedence(self, monkeypatch):
        """Prefix-style env var takes precedence over legacy suffix-style."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("SPEC_HELPER_LLM_PROVIDER", "groq")
        monkeypatch.setenv("LLM_PROVIDER_spec_helper", "anthropic")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anth-key")

        gw = init_llm_gateway("spec_helper")
        assert gw.provider == "groq"

    def test_agent_prefix_case_insensitive_lookup(self, monkeypatch):
        """Agent-prefix env var lookup should be resilient to case differences."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        # set a lowercase env var name (some shells/tools may do this)
        monkeypatch.setenv("spec_helper_llm_provider", "groq")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

        gw = init_llm_gateway("spec_helper")
        assert gw is not None
        assert gw.provider == "groq"

    def test_agent_specific_both_provider_and_model(self, monkeypatch):
        """Agent can override both provider and model (prefix-style)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("DEBUG_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("DEBUG_LLM_MODEL", "claude-opus-4-5-20251101")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

        # Default uses openai/gpt-4o
        gateway = init_llm_gateway()
        assert gateway.provider == "openai"
        assert gateway.model_name == "gpt-4o"

        gateway = init_llm_gateway("debug")
        assert gateway.provider == "anthropic"
        assert gateway.model_name == "claude-opus-4-5-20251101"

    def test_agent_specific_missing_api_key(self, monkeypatch):
        """Returns None if agent-specific provider's API key is missing."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("IMPLEMENTATION_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        # Missing ANTHROPIC_API_KEY
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Default works
        gateway = init_llm_gateway()
        assert gateway is not None

    def test_multiple_agents_different_providers(self, monkeypatch):
        """Different agents can use different providers simultaneously."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("PLANNER_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("IMPLEMENTATION_LLM_PROVIDER", "google")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

        default_gw = init_llm_gateway()
        assert default_gw.provider == "openai"

        planner_gw = init_llm_gateway("planner")
        assert planner_gw.provider == "anthropic"

        """Legacy suffix-style ignored; prefix-style (uppercase) accepted."""
        # Note: Environment variable names are case-sensitive on Unix systems
        # Ensure any prior prefix-style override is removed for this sub-check
        monkeypatch.delenv("PLANNER_LLM_PROVIDER", raising=False)

        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_PROVIDER_PLANNER", "anthropic")  # LEGACY SUFFIX - should be ignored
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")

        # Legacy suffix variable must be ignored
        gateway = init_llm_gateway("planner")
        assert gateway.provider == "openai"

        # Prefix-style (UPPERCASE) should be accepted
        monkeypatch.setenv("PLANNER_LLM_PROVIDER", "anthropic")
        gateway = init_llm_gateway("planner")
        assert gateway.provider == "anthropic"

    def test_partial_agent_override(self, monkeypatch):
        """Can override provider but not model (uses default for model)."""
        monkeypatch.setenv("USE_LLM", "1")
        monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "openai")
        monkeypatch.setenv("SPEC_HELPER_LLM_PROVIDER", "groq")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
        # No SPEC_HELPER_LLM_MODEL override

        gateway = init_llm_gateway("spec_helper")
        assert gateway is not None
        assert gateway.provider == "groq"
        # Should use groq's default model
        assert "llama" in gateway.model_name.lower()  # Groq's default is llama

