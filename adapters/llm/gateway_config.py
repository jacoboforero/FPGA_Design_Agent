"""
Centralized gateway configuration (opt-in, advanced mode).

This module provides tier-based gateway selection for advanced use cases.
Requires USE_GATEWAY_CONFIG=1 to be enabled - disabled by default.

For simple provider/model selection, use legacy mode with LLM_PROVIDER and LLM_MODEL
environment variables (see llm_gateway.py).

This module provides a factory for creating LLM gateways based on:
- Agent type (planner, implementation, debug, etc.)
- Gateway tier (local, fast, budget, balanced, powerful)
- Available API keys

Usage (only when USE_GATEWAY_CONFIG=1):
    from adapters.llm.gateway_config import get_gateway_for_agent
    
    gateway = get_gateway_for_agent("implementation")
    response = await gateway.generate(messages)
"""

import os
import logging
from typing import Optional, Dict, Any
from enum import Enum

from adapters.llm.gateway import LLMGateway
from adapters.llm.adapter_openai import OpenAIGateway
from adapters.llm.adapter_anthropic import AnthropicGateway
from adapters.llm.adapter_groq import GroqGateway
from adapters.llm.adapter_qwen34b import Qwen34BLocalGateway
from adapters.llm.adapter_google import GoogleGeminiGateway
from adapters.llm.adapter_cohere import CohereGateway

logger = logging.getLogger(__name__)


class GatewayTier(str, Enum):
    """Gateway performance/cost tiers."""
    LOCAL = "local"           # Free, local inference (Qwen3:4b)
    FAST = "fast"             # Ultra-fast, cheap (Groq)
    BUDGET = "budget"         # Cost-optimized cloud (GPT-4o-mini, Gemini Flash)
    BALANCED = "balanced"     # Good balance (Claude Sonnet, GPT-4.1)
    POWERFUL = "powerful"     # Most capable (GPT-5, Claude Opus)


class GatewayConfig:
    """
    Gateway configuration based on environment and agent requirements.
    """
    
    # Agent -> Tier mapping
    # This defines which tier each agent should use by default
    AGENT_TIER_MAP = {
        # Planning and architecture need powerful reasoning
        "planner": GatewayTier.POWERFUL,
        
        # Implementation benefits from strong code generation
        "implementation": GatewayTier.BALANCED,
        
        # Testbench generation similar to implementation
        "testbench": GatewayTier.BALANCED,
        
        # Debug needs strong analysis capabilities
        "debug": GatewayTier.POWERFUL,
        
        # Reflection for code review
        "reflection": GatewayTier.BALANCED,
        
        # Spec helper for simple assistance
        "spec_helper": GatewayTier.BUDGET,
        
        # Simple lint fixes can use fast models
        "lint_fix": GatewayTier.FAST,
        
        # Distillation of results
        "distill": GatewayTier.BUDGET,
    }
    
    def __init__(self):
        """Initialize gateway config from environment."""
        self.use_llm = os.getenv("USE_LLM", "0") == "1"
        
        # API keys
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.cohere_key = os.getenv("COHERE_API_KEY")
        
        # Ollama config
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        
        # Model overrides (optional)
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        self.google_model = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        
        # Cost tracking
        self.max_cost_per_task = float(os.getenv("MAX_COST_PER_TASK", "1.0"))
        
        # Tier preference (can override default agent mapping)
        tier_override = os.getenv("GATEWAY_TIER")
        self.tier_override = GatewayTier(tier_override) if tier_override else None
    
    def get_gateway_for_tier(self, tier: GatewayTier) -> Optional[LLMGateway]:
        """
        Get a gateway instance for the specified tier.
        
        Returns None if required API keys are not available.
        """
        try:
            if tier == GatewayTier.LOCAL:
                return self._create_local_gateway()
            
            elif tier == GatewayTier.FAST:
                return self._create_fast_gateway()
            
            elif tier == GatewayTier.BUDGET:
                return self._create_budget_gateway()
            
            elif tier == GatewayTier.BALANCED:
                return self._create_balanced_gateway()
            
            elif tier == GatewayTier.POWERFUL:
                return self._create_powerful_gateway()
            
            else:
                logger.error(f"Unknown tier: {tier}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create gateway for tier {tier}: {e}")
            return None
    
    def get_gateway_for_agent(self, agent_type: str) -> Optional[LLMGateway]:
        """
        Get appropriate gateway for an agent type.
        
        Args:
            agent_type: Agent identifier (e.g., "planner", "implementation")
            
        Returns:
            LLMGateway instance or None if LLMs disabled or keys missing
        """
        if not self.use_llm:
            logger.info("LLMs disabled (USE_LLM=0)")
            return None
        
        # Use tier override if set
        tier = self.tier_override or self.AGENT_TIER_MAP.get(
            agent_type,
            GatewayTier.BALANCED  # default
        )
        
        gateway = self.get_gateway_for_tier(tier)
        
        if gateway:
            logger.info(
                f"Created gateway for agent '{agent_type}': "
                f"{gateway.provider}/{gateway.model_name} (tier: {tier.value})"
            )
        else:
            logger.warning(
                f"Could not create gateway for agent '{agent_type}' "
                f"(tier: {tier.value}). Check API keys."
            )
        
        return gateway
    
    def _create_local_gateway(self) -> LLMGateway:
        """Create local Ollama gateway (Qwen3:4b)."""
        return Qwen34BLocalGateway(ollama_base_url=self.ollama_url)
    
    def _create_fast_gateway(self) -> Optional[LLMGateway]:
        """Create ultra-fast gateway (Groq with Llama)."""
        if self.groq_key:
            return GroqGateway(api_key=self.groq_key, model=self.groq_model)
        
        # Fallback to local if Groq unavailable
        logger.warning("Groq API key not available, falling back to local")
        return self._create_local_gateway()
    
    def _create_budget_gateway(self) -> Optional[LLMGateway]:
        """Create budget-tier gateway (cheap cloud models)."""
        # Prefer Google Gemini Flash (very cost-effective)
        if self.google_key:
            return GoogleGeminiGateway(
                api_key=self.google_key,
                model="gemini-2.0-flash"
            )
        
        # OpenAI mini models
        if self.openai_key:
            return OpenAIGateway(
                api_key=self.openai_key,
                model="gpt-4o-mini"
            )
        
        # Groq as fallback
        if self.groq_key:
            return GroqGateway(api_key=self.groq_key, model=self.groq_model)
        
        # Last resort: local
        logger.warning("No budget cloud gateways available, using local")
        return self._create_local_gateway()
    
    def _create_balanced_gateway(self) -> Optional[LLMGateway]:
        """Create balanced gateway (good performance/cost)."""
        # Prefer Anthropic Claude Sonnet (excellent for code)
        if self.anthropic_key:
            return AnthropicGateway(
                api_key=self.anthropic_key,
                model=self.anthropic_model
            )
        
        # OpenAI GPT-4o as alternative
        if self.openai_key:
            return OpenAIGateway(
                api_key=self.openai_key,
                model=self.openai_model
            )
        
        # Google Gemini Pro
        if self.google_key:
            return GoogleGeminiGateway(
                api_key=self.google_key,
                model="gemini-2.0-pro"
            )
        
        # Fallback to budget tier
        logger.warning("No balanced gateways available, falling back to budget")
        return self._create_budget_gateway()
    
    def _create_powerful_gateway(self) -> Optional[LLMGateway]:
        """Create most powerful gateway (best models)."""
        # OpenAI GPT-5 (if you have access)
        if self.openai_key and "gpt-5" in self.openai_model:
            return OpenAIGateway(
                api_key=self.openai_key,
                model=self.openai_model
            )
        
        # Claude Opus 4.5
        if self.anthropic_key:
            return AnthropicGateway(
                api_key=self.anthropic_key,
                model="claude-opus-4-5-20251101"
            )
        
        # Fallback to balanced
        logger.warning("No powerful gateways available, falling back to balanced")
        return self._create_balanced_gateway()
    
    def get_fallback_chain(self, agent_type: str) -> list[LLMGateway]:
        """
        Get a chain of gateways for fallback on failure.
        
        Returns list from primary to fallback options.
        """
        tier = self.AGENT_TIER_MAP.get(agent_type, GatewayTier.BALANCED)
        chain = []
        
        # Primary gateway
        primary = self.get_gateway_for_tier(tier)
        if primary:
            chain.append(primary)
        
        # Fallback tiers
        if tier == GatewayTier.POWERFUL:
            fallback = self.get_gateway_for_tier(GatewayTier.BALANCED)
            if fallback:
                chain.append(fallback)
        
        if tier in (GatewayTier.POWERFUL, GatewayTier.BALANCED):
            fallback = self.get_gateway_for_tier(GatewayTier.BUDGET)
            if fallback:
                chain.append(fallback)
        
        # Always fallback to local if available
        if tier != GatewayTier.LOCAL:
            local = self.get_gateway_for_tier(GatewayTier.LOCAL)
            if local and local not in chain:
                chain.append(local)
        
        return chain


# Global config instance
_config: Optional[GatewayConfig] = None


def get_config() -> GatewayConfig:
    """Get the global gateway configuration."""
    global _config
    if _config is None:
        _config = GatewayConfig()
    return _config


def get_gateway_for_agent(agent_type: str) -> Optional[LLMGateway]:
    """
    Convenience function to get gateway for an agent type.
    
    Args:
        agent_type: Agent identifier (e.g., "planner", "implementation")
        
    Returns:
        LLMGateway instance or None
    """
    return get_config().get_gateway_for_agent(agent_type)


def get_fallback_chain(agent_type: str) -> list[LLMGateway]:
    """
    Get fallback chain for an agent.
    
    Returns list of gateways from primary to fallback.
    """
    return get_config().get_fallback_chain(agent_type)
