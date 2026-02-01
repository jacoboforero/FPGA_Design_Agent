"""
Common LLM gateway initialization for agents.

This module provides the gateway factory used throughout the agent system.
Supports both legacy direct initialization and new centralized configuration.
"""

import os
import logging
from typing import Optional

from adapters.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)


def init_llm_gateway(agent_type: Optional[str] = None) -> Optional[LLMGateway]:
    """
    Initialize an LLM gateway for the specified agent type.
    
    This function supports two modes:
    1. New mode (USE_GATEWAY_CONFIG=1): Uses centralized gateway_config.py
    2. Legacy mode (default): Direct initialization for backward compatibility
    
    Args:
        agent_type: Agent identifier (e.g., "planner", "implementation")
                   If None, uses a balanced default gateway.
    
    Returns:
        LLMGateway instance or None if LLMs are disabled or keys missing
    
    Environment Variables:
        USE_LLM: Set to "1" to enable LLM usage (default: "0")
        USE_GATEWAY_CONFIG: Set to "1" to use centralized config (default: "0")
        
        # For centralized config mode:
        OPENAI_API_KEY: OpenAI API key
        ANTHROPIC_API_KEY: Anthropic API key
        GOOGLE_API_KEY: Google API key
        GROQ_API_KEY: Groq API key
        OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
        GATEWAY_TIER: Override tier selection (local|fast|budget|balanced|powerful)
        
        # For legacy mode:
        LLM_PROVIDER: Provider to use (openai|anthropic|google|groq|qwen3-local)
        LLM_MODEL: Model name to use
    
    Examples:
        # Centralized config (recommended for new code)
        export USE_LLM=1
        export USE_GATEWAY_CONFIG=1
        export ANTHROPIC_API_KEY=xxx
        gateway = init_llm_gateway("planner")  # Auto-selects powerful model
        
        # Legacy mode (backward compatible)
        export USE_LLM=1
        export LLM_PROVIDER=openai
        export LLM_MODEL=gpt-4o
        export OPENAI_API_KEY=xxx
        gateway = init_llm_gateway()
    """
    use_llm = os.getenv("USE_LLM", "0") == "1"
    
    if not use_llm:
        logger.info("LLMs disabled (USE_LLM != 1)")
        return None
    
    # Check if using new centralized config
    use_config = os.getenv("USE_GATEWAY_CONFIG", "0") == "1"
    
    if use_config:
        return _init_with_config(agent_type)
    else:
        return _init_legacy(agent_type)


def _init_with_config(agent_type: Optional[str]) -> Optional[LLMGateway]:
    """Initialize using centralized gateway_config.py"""
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
    Legacy initialization method for backward compatibility.
    
    Uses LLM_PROVIDER and LLM_MODEL environment variables.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
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
    Initialize an LLM gateway with fallback support.
    
    Only works in USE_GATEWAY_CONFIG=1 mode.
    Returns the primary gateway, but you can get the full fallback
    chain using get_fallback_chain().
    
    Args:
        agent_type: Agent identifier
        
    Returns:
        Primary gateway or None
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
