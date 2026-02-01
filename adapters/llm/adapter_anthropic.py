"""
Anthropic Claude implementation of the LLM Gateway interface.

Supports Claude 3 and Claude 4 model families.
"""

from typing import Optional, List
import anthropic
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)


class AnthropicGateway(LLMGateway):
    """
    Gateway implementation for Anthropic's Claude models.
    
    Supports:
    - Claude 4.5 (Opus, Sonnet, Haiku)
    - Claude 3.5 (Opus, Sonnet, Haiku) 
    - Claude 3 (Opus, Sonnet, Haiku)
    """
    
    # Pricing per million tokens (as of January 2025)
    PRICING = {
        # Claude 4.5 family
        "claude-opus-4-5": {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
        "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
        
        # Claude 3.5 family
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
        
        # Claude 3 family (legacy)
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
    }
    
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250929",
    ):
        """
        Initialize Anthropic gateway.
        
        Args:
            api_key: Anthropic API key
            model: Model identifier (e.g., "claude-sonnet-4-5-20250929")
        """
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Anthropic's Messages API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Anthropic requires system messages separately
        system_content, conversation_messages = self._convert_messages(messages)
        
        # Build API parameters
        api_params = {
            "model": self._model,
            "messages": conversation_messages,
            "max_tokens": config.max_tokens or 4096,  # Required parameter
        }
        
        # Add system message if present
        if system_content:
            api_params["system"] = system_content
        
        # Add optional parameters
        if config.temperature is not None:
            api_params["temperature"] = config.temperature
        if config.top_p is not None:
            api_params["top_p"] = config.top_p
        if config.top_k is not None:
            api_params["top_k"] = config.top_k
        if config.stop_sequences:
            api_params["stop_sequences"] = config.stop_sequences
        
        # Add provider-specific parameters
        api_params.update(config.provider_specific)
        
        try:
            # Make API call
            response = await self.client.messages.create(**api_params)
            
            # Convert to our standard format
            model_response = self._convert_response(response)
            
            return model_response
            
        except anthropic.RateLimitError as e:
            raise RuntimeError(f"Anthropic rate limit exceeded: {e}")
        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error calling Anthropic: {e}")
    
    @property
    def model_name(self) -> str:
        """The Anthropic model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'anthropic'."""
        return "anthropic"
    
    @property
    def supports_files(self) -> bool:
        """Claude supports vision for all Claude 3+ models."""
        return "claude-3" in self._model or "claude-4" in self._model
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Anthropic.
        
        Anthropic constraints:
        - temperature: [0, 1]
        - top_p: [0, 1]
        - top_k: [1, infinity]
        - max_tokens: required, varies by model (typically 4096-200K)
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 1:
                raise ValueError("Anthropic temperature must be in [0, 1]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Anthropic top_p must be in [0, 1]")
        
        if config.top_k is not None:
            if config.top_k < 1:
                raise ValueError("Anthropic top_k must be >= 1")
        
        # max_tokens is required by Anthropic
        if config.max_tokens is None:
            config.max_tokens = 4096  # Reasonable default
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Anthropic pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model
        pricing_key = None
        
        # Check for exact model family matches (longest first to avoid substring issues)
        model_families = sorted(self.PRICING.keys(), key=len, reverse=True)
        for family in model_families:
            if family in response.model_name:
                pricing_key = family
                break
        
        if not pricing_key:
            return 0.0  # Unknown model
        
        pricing = self.PRICING[pricing_key]
        
        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _convert_messages(self, messages: List[Message]) -> tuple[str, List[dict]]:
        """
        Convert messages to Anthropic format.
        
        Anthropic requires:
        - System messages passed separately via 'system' parameter
        - Conversation must alternate user/assistant
        - Cannot have consecutive messages from same role
        
        Returns:
            (system_content, conversation_messages)
        """
        system_content = ""
        conversation_messages = []
        
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Accumulate system messages
                if system_content:
                    system_content += "\n\n"
                system_content += msg.content
            else:
                # Handle file attachments
                content = msg.content
                if msg.attachments:
                    file_contents = []
                    for attachment in msg.attachments:
                        if "content" in attachment:
                            filename = attachment.get("filename", "file")
                            file_contents.append(f"\n\n--- {filename} ---\n{attachment['content']}")
                        elif "path" in attachment:
                            try:
                                with open(attachment["path"], "r") as f:
                                    file_content = f.read()
                                    filename = attachment.get("filename", attachment["path"])
                                    file_contents.append(f"\n\n--- {filename} ---\n{file_content}")
                            except Exception as e:
                                file_contents.append(f"\n\n[Error reading {attachment['path']}: {e}]")
                    
                    if file_contents:
                        content = content + "".join(file_contents)
                
                conversation_messages.append({
                    "role": msg.role.value,
                    "content": content,
                })
        
        # Anthropic requires alternating roles - merge consecutive same-role messages
        merged_messages = []
        for msg in conversation_messages:
            if merged_messages and merged_messages[-1]["role"] == msg["role"]:
                # Merge with previous message
                merged_messages[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged_messages.append(msg)
        
        # Ensure conversation starts with user message
        if merged_messages and merged_messages[0]["role"] != "user":
            merged_messages.insert(0, {"role": "user", "content": "(Starting conversation)"})
        
        return system_content, merged_messages
    
    def _convert_response(self, anthropic_response) -> ModelResponse:
        """Convert Anthropic response to our ModelResponse format."""
        # Extract content (handle both text and content blocks)
        content = ""
        if hasattr(anthropic_response.content, '__iter__'):
            for block in anthropic_response.content:
                if hasattr(block, 'text'):
                    content += block.text
        else:
            content = str(anthropic_response.content)
        
        # Extract token usage
        input_tokens = anthropic_response.usage.input_tokens
        output_tokens = anthropic_response.usage.output_tokens
        total_tokens = input_tokens + output_tokens
        
        # Estimate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=anthropic_response.model,
            provider="anthropic",
        )
        cost = self.estimate_cost(temp_response)
        
        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=anthropic_response.model,
            provider="anthropic",
            finish_reason=anthropic_response.stop_reason,
            estimated_cost_usd=cost,
            raw_response=anthropic_response.model_dump() if hasattr(anthropic_response, 'model_dump') else {},
        )
    
    async def close(self):
        """Clean up the async client."""
        await self.client.close()
