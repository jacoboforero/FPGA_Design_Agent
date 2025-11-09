# Abstraction layer for LLM API calls.

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timezone

# Standard message roles across providers.
class MessageRole(str, Enum): 
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

# Message from conversation log.
class Message(BaseModel):
    role: MessageRole
    content: str
    
    # Multimodal models allow for additional files to be transmitted.
    attachments: List[Dict[str, Any]] = Field(default_factory=list)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# Provider-agnostic Response packet including base response and metadata.
class ModelResponse(BaseModel):
    content: str
    
    # Token usage and cost accounting.
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: Optional[float] = None
    
    
    model_name: str # "gpt-5", "qwen3:8b", etc.
    provider: str # "openai", "anthropic", "google", etc.
    
    # "Exit Code" for the LLM call. "stop", "length", etc.
    finish_reason: Optional[str] = None
    
    # Raw response from LLM call to assist debugging or human escalation states.
    raw_response: Dict[str, Any] = Field(default_factory=dict)
    
    # Per-instance timestamping via factory.
    timestamp: datetime = Field(default_factory=utc_now)


class GenerationConfig(BaseModel):
    # Adapter implementations handle mapping to provider-specific params.
    
    max_tokens: Optional[int] = None
    
    # Sampling methodologies (note, some subsets of these ARE mutually exclusive).
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    
    # Terminal character sequences.
    stop_sequences: List[str] = Field(default_factory=list)
    
    # Provider-specific overrides.
    provider_specific: Dict[str, Any] = Field(default_factory=dict)


class LLMGateway(ABC): # Abstract gateway for calling LLM APIs.
    
    """
        Generate a response from the LLM.
        
        Args:
            messages: Conversation log (role-labeled messages)
            config: Generation parameters (temperature, max_tokens, etc.)
            
        Returns:
            ModelResponse with content, token counts, and metadata
        """
    @abstractmethod
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier (e.g., "gpt-5", "claude-3-opus-20240229")."""
        pass
    
    @property
    @abstractmethod
    def provider(self) -> str:
        """The provider name (e.g., "openai", "anthropic", "google")."""
        pass
    
    @property
    @abstractmethod
    def supports_files(self) -> bool:
        """Whether this gateway supports file attachments in messages."""
        pass
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Override to enforce provider-specific constraints like:
        - OpenAI: temperature in [0, 2]
        - Anthropic: temperature in [0, 1]
        - Mutually exclusive parameters
        
        Args:
            config: Input configuration
            
        Returns:
            Validated/normalized configuration
            
        Raises:
            ValueError: If config is invalid for this provider
        """
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Override with provider-specific pricing. Default returns 0.
        
        Args:
            response: The model response with token counts
            
        Returns:
            Estimated cost in USD
        """
        return 0.0


# ============================================================================
# Utility function for quick single-message generation
# ============================================================================

async def quick_generate(
    gateway: LLMGateway,
    prompt: str,
    system_prompt: Optional[str] = None,
    config: Optional[GenerationConfig] = None,
) -> ModelResponse:
    """
    Args:
        gateway: The LLM gateway to use
        prompt: User prompt
        system_prompt: Optional system prompt
        config: Generation configuration
        
    Returns:
        ModelResponse
    """
    messages = []
    if system_prompt:
        # Many agentic workflows tell the agent "what is is/does" before feeding it subsequent prompts.
        messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
    messages.append(Message(role=MessageRole.USER, content=prompt))
    
    return await gateway.generate(messages=messages, config=config)