"""
Common LLM gateway initialization for agents.

This module provides the gateway factory used throughout the agent system.
Defaults to simple environment-based configuration for backward compatibility.
Supports optional centralized tier-based configuration for advanced use cases.
"""

import os
import logging
from typing import Optional

from adapters.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


def init_llm_gateway(agent_type: Optional[str] = None) -> Optional[LLMGateway]:
    """
    Initialize an LLM gateway.
    
    This function supports two modes:
    1. Legacy mode (default): Simple environment-based provider/model selection
    2. Config mode (USE_GATEWAY_CONFIG=1): Tier-based agent-aware selection
    
    Args:
        agent_type: Agent identifier (e.g., "planner", "implementation")
                   Used to look up agent-specific model overrides in legacy mode.
                   Ignored if not provided; may be used in future per-agent config.
    
    Returns:
        LLMGateway instance or None if LLMs are disabled or keys missing
    
    Environment Variables (Legacy Mode - default):
        USE_LLM: Set to "1" to enable LLM usage (default: "0")
        
        # Provider and model selection (simple):
        LLM_PROVIDER: Provider to use (openai|anthropic|google|groq|qwen3-local)
                     (default: "openai")
        LLM_MODEL: Model name to use (default varies by provider)
        
        # Per-agent overrides (optional, future feature):
        LLM_PROVIDER_{agent_type}: Provider for specific agent (e.g., LLM_PROVIDER_planner=anthropic)
        LLM_MODEL_{agent_type}: Model for specific agent (e.g., LLM_MODEL_planner=claude-opus)
        
        # API keys (required for each provider):
        OPENAI_API_KEY: OpenAI API key
        ANTHROPIC_API_KEY: Anthropic API key
        GOOGLE_API_KEY: Google API key
        GROQ_API_KEY: Groq API key
    
    Environment Variables (Config Mode - opt-in):
        USE_LLM: Set to "1" to enable LLM usage
        USE_GATEWAY_CONFIG: Set to "1" to use tier-based selection (default: "0")
        GATEWAY_TIER: Override tier (local|fast|budget|balanced|powerful)
    
    Examples:
        # Legacy mode (simple, recommended for most users):
        export USE_LLM=1
        export LLM_PROVIDER=openai
        export LLM_MODEL=gpt-4o
        export OPENAI_API_KEY=sk-...
        gateway = init_llm_gateway()
        
        # Config mode (advanced, tier-based):
        export USE_LLM=1
        export USE_GATEWAY_CONFIG=1
        export ANTHROPIC_API_KEY=sk-ant-...
        gateway = init_llm_gateway("planner")  # Auto-selects by tier
    """
    use_llm = os.getenv("USE_LLM", "0") == "1"
    
    if not use_llm:
        logger.info("LLMs disabled (USE_LLM != 1)")
        return None
    
    # Check if using advanced centralized config mode
    use_config = os.getenv("USE_GATEWAY_CONFIG", "0") == "1"
    
    if use_config:
        return _init_with_config(agent_type)
    else:
        return _init_legacy(agent_type)


def _init_with_config(agent_type: Optional[str]) -> Optional[LLMGateway]:
    """
    Initialize using centralized gateway_config (opt-in, advanced mode).
    
    Only used if USE_GATEWAY_CONFIG=1 is set. Provides tier-based agent-aware
    gateway selection. See gateway_config.py for details.
    """
    try:
        from adapters.llm.gateway_config import get_gateway_for_agent
        
        agent_type = agent_type or "balanced"
        gateway = get_gateway_for_agent(agent_type)
        
        if gateway is None:
            logger.warning(
                f"Failed to initialize gateway for '{agent_type}'. "
                "Check that required API keys are set."
            )
        
        return gateway
        
    except ImportError as e:
        logger.error(f"Cannot import gateway_config: {e}")
        logger.info("Falling back to legacy initialization")
        return _init_legacy(agent_type)


def _init_legacy(agent_type: Optional[str]) -> Optional[LLMGateway]:
    """
    Legacy initialization using environment variables.
    
    Environment variables (simple):
    - LLM_PROVIDER: Provider name (default: "openai")
    - LLM_MODEL: Model name (default varies by provider)
    
    Per-agent overrides (optional, for future use):
    - LLM_PROVIDER_{agent_type}: Override provider for specific agent
    - LLM_MODEL_{agent_type}: Override model for specific agent
    
    Example:
        LLM_PROVIDER=openai
        LLM_MODEL=gpt-4o
        LLM_PROVIDER_planner=anthropic
        LLM_MODEL_planner=claude-opus
        
        init_llm_gateway()  # Uses openai/gpt-4o
        init_llm_gateway("planner")  # Uses anthropic/claude-opus
    """
    # Check for agent-specific overrides first
    provider = None
    model = None
    
    if agent_type:
        provider = os.getenv(f"LLM_PROVIDER_{agent_type}").lower() if os.getenv(f"LLM_PROVIDER_{agent_type}") else None
        model = os.getenv(f"LLM_MODEL_{agent_type}")
    
    # Fall back to defaults
    if not provider:
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if not model:
        model = os.getenv("LLM_MODEL")
    
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
        
        elif provider in ("qwen3-local", "ollama", "local"):
            from adapters.llm.adapter_qwen34b import Qwen34BLocalGateway
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return Qwen34BLocalGateway(ollama_base_url=ollama_url)
        
        else:
            logger.error(f"Unknown LLM_PROVIDER: {provider}")
            return None
            
    except ImportError as e:
        logger.error(f"Failed to import adapter for {provider}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize {provider} gateway: {e}")
        return None


def init_llm_gateway_with_fallback(agent_type: str) -> Optional[LLMGateway]:
    """
    Initialize an LLM gateway with fallback support (config mode only).
    
    Only works when USE_GATEWAY_CONFIG=1. Returns the primary gateway for an agent,
    but also enables fallback chains if primary gateway fails.
    
    Args:
        agent_type: Agent identifier (e.g., "planner", "implementation")
        
    Returns:
        Primary gateway or None if none available
    """
    use_llm = os.getenv("USE_LLM", "0") == "1"
    if not use_llm:
        return None
    
    use_config = os.getenv("USE_GATEWAY_CONFIG", "0") == "1"
    if not use_config:
        logger.warning(
            "Fallback mode requires USE_GATEWAY_CONFIG=1. "
            "Falling back to standard initialization."
        )
        return init_llm_gateway(agent_type)
    
    try:
        from adapters.llm.gateway_config import get_fallback_chain
        
        chain = get_fallback_chain(agent_type)
        
        if not chain:
            logger.warning(f"No gateways available for '{agent_type}'")
            return None
        
        logger.info(
            f"Initialized gateway for '{agent_type}' with {len(chain)} fallback(s): "
            f"{' -> '.join(f'{g.provider}/{g.model_name}' for g in chain)}"
        )
        
        return chain[0]  # Return primary
        
    except ImportError as e:
        logger.error(f"Cannot import gateway_config: {e}")
        return init_llm_gateway(agent_type)
