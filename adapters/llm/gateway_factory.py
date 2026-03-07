"""
adapters.llm.gateway_factory — LLM gateway factory

Provides the runtime factory used by agents to initialize LLM gateways from
environment variables. This module contains `init_llm_gateway()` (primary
factory) and `init_llm_gateway_with_fallback()` (deprecated wrapper).

Note: centralized/tiered `gateway_config` support has been removed — legacy
env-var initialization is used exclusively.
"""

import os
import logging
from typing import Optional

from adapters.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


def init_llm_gateway(agent_type: Optional[str] = None) -> Optional[LLMGateway]:
    """
    Initialize an LLM gateway.
    
    Initialize an LLM gateway using legacy environment-variable configuration.
    
    Args:
        agent_type: Agent identifier (e.g., "planner", "implementation"). Used only
                    for per-agent environment overrides (if present).
    
    Returns:
        LLMGateway instance or None if LLMs are disabled or keys missing.
    
    Environment Variables:
        USE_LLM: Set to "1" to enable LLM usage (default: "0").

        DEFAULT_LLM_PROVIDER: Provider to use (openai|anthropic|google|groq|qwen-local)
                     (default: "openai").
        DEFAULT_LLM_MODEL: Model name to use (default varies by provider).

        Per-agent overrides (optional, **prefix-style only**):
        {AGENT}_LLM_PROVIDER, {AGENT}_LLM_MODEL (e.g. SPEC_HELPER_LLM_MODEL)

        API keys required per provider: OPENAI_API_KEY, ANTHROPIC_API_KEY,
        GOOGLE_API_KEY, GROQ_API_KEY.
    

    
    Examples:
        # Legacy mode (simple, recommended):
        export USE_LLM=1
        export DEFAULT_LLM_PROVIDER=openai
        export DEFAULT_LLM_MODEL=gpt-4o
        export OPENAI_API_KEY=sk-...
        gateway = init_llm_gateway()

        # Note: centralized/tiered gateway_config has been removed.
    """
    use_llm = os.getenv("USE_LLM", "0") == "1"
    
    if not use_llm:
        logger.info("LLMs disabled (USE_LLM != 1)")
        return None
    
    # Legacy-only initialization (tiered gateway_config removed).
    return _init_legacy(agent_type)


# Centralized `gateway_config` support has been removed — legacy
# environment-variable based initialization is used exclusively.
# (The former `_init_with_config` implementation was removed.)


def _init_legacy(agent_type: Optional[str]) -> Optional[LLMGateway]:
    """
    Legacy initialization using environment variables.
    
    Environment variables (simple):
    - DEFAULT_LLM_PROVIDER: Provider name (default: "openai")
    - DEFAULT_LLM_MODEL: Model name (default varies by provider)
    
    Per-agent overrides (optional):
    - {AGENT}_LLM_PROVIDER: Override provider for specific agent (e.g. PLANNER_LLM_PROVIDER)
    - {AGENT}_LLM_MODEL: Override model for specific agent (e.g. PLANNER_LLM_MODEL)

    Example:
        DEFAULT_LLM_PROVIDER=openai
        DEFAULT_LLM_MODEL=gpt-4o
        PLANNER_LLM_PROVIDER=anthropic
        PLANNER_LLM_MODEL=claude-opus

        init_llm_gateway()  # Uses openai/gpt-4o
        init_llm_gateway("planner")  # Uses anthropic/claude-opus
    """
    # Check for agent-specific overrides first (supports both legacy suffix-style and new prefix-style)
    provider = None
    model = None

    if agent_type:
        agent_upper = agent_type.upper()
        agent_lower = agent_type.lower()

        # Candidate keys for prefix-style env vars (handle common variants)
        provider_keys = [
            f"{agent_upper}_LLM_PROVIDER",
            f"{agent_lower}_LLM_PROVIDER",
            f"{agent_upper.replace('-', '_')}_LLM_PROVIDER",
            f"{agent_lower.replace('-', '_')}_LLM_PROVIDER",
        ]
        model_keys = [
            f"{agent_upper}_LLM_MODEL",
            f"{agent_lower}_LLM_MODEL",
            f"{agent_upper.replace('-', '_')}_LLM_MODEL",
            f"{agent_lower.replace('-', '_')}_LLM_MODEL",
        ]

        # Prefer exact-case matches first (fast-path)
        provider = next((os.getenv(k) for k in provider_keys if os.getenv(k)), None)
        model = next((os.getenv(k) for k in model_keys if os.getenv(k)), None)

        # If not found, do a case-insensitive search across environment keys
        if not provider:
            target = f"{agent_lower}_llm_provider"
            for k, v in os.environ.items():
                if k.lower() == target:
                    provider = v
                    break
        if not model:
            target_model = f"{agent_lower}_llm_model"
            for k, v in os.environ.items():
                if k.lower() == target_model:
                    model = v
                    break

        # Normalize and trim values to be resilient to whitespace/case
        provider = provider.strip().lower() if isinstance(provider, str) and provider.strip() else None
        model = model.strip() if isinstance(model, str) and model.strip() else None

    # Fall back to defaults (normalize whitespace/case)
    if not provider:
        provider = (os.getenv("DEFAULT_LLM_PROVIDER", "openai") or "openai").strip().lower()
    if not model:
        model = os.getenv("DEFAULT_LLM_MODEL")
        model = model.strip() if isinstance(model, str) and model.strip() else None
    
    try:
        if provider == "openai":
            from adapters.llm.adapter_openai import OpenAIGateway
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not set")
                return None
            model = model or "gpt-4o"
            return OpenAIGateway(api_key=api_key, model=model)
        
        elif provider == "anthropic":
            from adapters.llm.adapter_anthropic import AnthropicGateway
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY not set")
                return None
            model = model or "claude-sonnet-4-5-20250929"
            return AnthropicGateway(api_key=api_key, model=model)
        
        elif provider == "google":
            from adapters.llm.adapter_google import GoogleGeminiGateway
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                logger.error("GOOGLE_API_KEY not set")
                return None
            model = model or "gemini-2.0-flash"
            return GoogleGeminiGateway(api_key=api_key, model=model)
        
        elif provider == "groq":
            from adapters.llm.adapter_groq import GroqGateway
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                logger.error("GROQ_API_KEY not set")
                return None
            model = model or "llama-3.1-8b-instant"
            return GroqGateway(api_key=api_key, model=model)
        
        elif provider in ("qwen-local",):
            from adapters.llm.adapter_qwen import QwenLocalGateway

            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            # Allow selecting the local Qwen model via DEFAULT_LLM_MODEL (per-agent overrides supported)
            selected_model = model or "qwen3:4b"
            return QwenLocalGateway(model=selected_model, ollama_base_url=ollama_url)
        
        else:
            logger.error(f"Unknown DEFAULT_LLM_PROVIDER: {provider}")
            return None
            
    except ImportError as e:
        logger.error(f"Failed to import adapter for {provider}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize {provider} gateway: {e}")
        return None


def init_llm_gateway_with_fallback(agent_type: str) -> Optional[LLMGateway]:
    """
    Backwards-compatible wrapper: fallback chains and centralized config were removed.
    This now delegates to init_llm_gateway() (legacy initialization).
    """
    logger.warning(
        "init_llm_gateway_with_fallback deprecated — centralized gateway_config/"
        "fallback removed; using legacy init."
    )
    return init_llm_gateway(agent_type)
