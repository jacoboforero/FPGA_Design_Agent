"""
Grok (xAI) implementation of the LLM Gateway interface.

Grok uses OpenAI-compatible API, so this adapter is similar to OpenAI
but with Grok-specific models and pricing.
"""

from typing import Optional, List
from openai import AsyncOpenAI
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)


class GrokGateway(LLMGateway):
    """
    Gateway implementation for xAI's Grok models.
    
    Grok uses an OpenAI-compatible API but with different models and pricing.
    
    Supports:
    - grok-2 (latest, most capable)
    - grok-2-mini (faster, more efficient)
    - grok-1 (legacy)
    """
    
    # Pricing per million tokens (as of January 2025)
    # Note: xAI pricing may vary - check https://x.ai/api for latest
    PRICING = {
        "grok-2": {"input": 2.00, "output": 10.00},
        "grok-2-mini": {"input": 0.50, "output": 2.00},
        "grok-1": {"input": 5.00, "output": 15.00},
    }
    
    # xAI API endpoint
    GROK_BASE_URL = "https://api.x.ai/v1"
    
    def __init__(
        self,
        api_key: str,
        model: str = "grok-2-mini",
    ):
        """
        Initialize Grok gateway.
        
        Args:
            api_key: xAI API key
            model: Model identifier (e.g., "grok-2", "grok-2-mini")
        """
        # Use OpenAI client with xAI's endpoint
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.GROK_BASE_URL,
        )
        self._model = model
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Grok's chat completion API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert our Message format to OpenAI-compatible format
        grok_messages = self._convert_messages(messages)
        
        # Build API parameters
        api_params = {
            "model": self._model,
            "messages": grok_messages,
        }
        
        # Add optional parameters
        if config.temperature is not None:
            api_params["temperature"] = config.temperature
        if config.top_p is not None:
            api_params["top_p"] = config.top_p
        if config.max_tokens is not None:
            api_params["max_tokens"] = config.max_tokens
        if config.stop_sequences:
            api_params["stop"] = config.stop_sequences

        # Pass through typed generation fields
        if getattr(config, "functions", None) is not None:
            api_params["functions"] = config.functions
        if getattr(config, "function_call", None) is not None:
            api_params["function_call"] = config.function_call
        if getattr(config, "n", None) is not None:
            api_params["n"] = config.n
        if getattr(config, "logprobs", None) is not None:
            api_params["logprobs"] = config.logprobs
        if getattr(config, "user", None) is not None:
            api_params["user"] = config.user
        if getattr(config, "stream", None) is not None:
            api_params["stream"] = config.stream

        # Add provider-specific parameters
        api_params.update(config.provider_specific)
        
        try:
            # Make API call
            response = await self.client.chat.completions.create(**api_params)
            
            # Convert to our standard format
            model_response = self._convert_response(response)
            
            return model_response
            
        except Exception as e:
            # OpenAI client will raise various exceptions
            if "rate" in str(e).lower():
                raise RuntimeError(f"Grok rate limit exceeded: {e}")
            else:
                raise RuntimeError(f"Grok API error: {e}")
    
    @property
    def model_name(self) -> str:
        """The Grok model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'grok'."""
        return "grok"
    
    @property
    def supports_files(self) -> bool:
        """Grok-2 supports vision capabilities."""
        return "grok-2" in self._model
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Grok.
        
        Grok uses OpenAI-compatible parameters:
        - temperature: [0, 2]
        - top_p: [0, 1]
        - top_k not supported
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("Grok temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Grok top_p must be in [0, 1]")
        
        if config.top_k is not None:
            raise ValueError("Grok does not support top_k parameter")
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Grok pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model
        pricing_key = None
        
        # Match model family (longest first to avoid substring issues)
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
    
    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert our Message format to OpenAI-compatible format used by Grok."""
        grok_messages = []
        
        for msg in messages:
            grok_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            
            # Handle file attachments - append their text content to the message
            if msg.attachments:
                file_contents = []
                for attachment in msg.attachments:
                    if "content" in attachment:
                        filename = attachment.get("filename", "file")
                        file_contents.append(f"\n\n--- {filename} ---\n{attachment['content']}")
                    elif "path" in attachment:
                        try:
                            with open(attachment["path"], "r") as f:
                                content = f.read()
                                filename = attachment.get("filename", attachment["path"])
                                file_contents.append(f"\n\n--- {filename} ---\n{content}")
                        except Exception as e:
                            file_contents.append(f"\n\n[Error reading {attachment['path']}: {e}]")
                
                if file_contents:
                    grok_msg["content"] = msg.content + "".join(file_contents)
            
            grok_messages.append(grok_msg)
        
        return grok_messages
    
    def _convert_response(self, grok_response) -> ModelResponse:
        """Convert Grok (OpenAI-compatible) response to our ModelResponse format."""
        choice = grok_response.choices[0]
        content = choice.message.content or ""
        
        # Extract token usage
        usage = grok_response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens
        
        # Estimate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="grok",
        )
        cost = self.estimate_cost(temp_response)

        raw = grok_response.model_dump() if hasattr(grok_response, 'model_dump') else {}
        function_call = None
        choices = None
        if isinstance(raw, dict):
            choices = raw.get("choices")
            function_call = raw.get("function_call") or raw.get("tool_call")

        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=grok_response.model,
            provider="grok",
            finish_reason=choice.finish_reason,
            estimated_cost_usd=cost,
            raw_response=raw,
            choices=choices,
            function_call=function_call,
        )
    
    async def close(self):
        """Clean up the async client."""
        await self.client.close()
