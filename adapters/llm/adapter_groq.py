"""
Groq implementation of the LLM Gateway interface (OpenAI-compatible API).

Groq provides ultra-fast inference with Llama models via OpenAI-compatible endpoint.
"""

from typing import Optional, List
import logging
from openai import AsyncOpenAI
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)

logger = logging.getLogger(__name__)


class GroqGateway(LLMGateway):
    """
    Gateway for Groq's ultra-fast LLM inference.
    
    Uses OpenAI-compatible endpoint with Llama models.
    Groq excels at:
    - Very low latency (tokens/second)
    - Cost-effective inference
    - Good for high-throughput RTL generation
    """
    
    # Pricing per 1M tokens (as of January 2025)
    # Note: Groq pricing is very competitive
    PRICING = {
        "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
        "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
        "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
        "llama-3.2-90b-text-preview": {"input": 0.90, "output": 0.90},
        "llama-3.2-11b-text-preview": {"input": 0.18, "output": 0.18},
        "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    }
    
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    
    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.1-8b-instant",
    ):
        """
        Initialize Groq gateway.
        
        Args:
            api_key: Groq API key (get from https://console.groq.com)
            model: Model identifier (e.g., "llama-3.1-8b-instant")
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.GROQ_BASE_URL,
        )
        self._model = model
        self.logger = logger
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Groq's ultra-fast inference."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert messages
        groq_messages = self._convert_messages(messages)
        
        # Build API parameters
        api_params = {
            "model": self._model,
            "messages": groq_messages,
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
            error_msg = str(e).lower()
            if "rate" in error_msg or "limit" in error_msg:
                raise RuntimeError(f"Groq rate limit exceeded: {e}")
            elif "quota" in error_msg:
                raise RuntimeError(f"Groq quota exceeded: {e}")
            else:
                raise RuntimeError(f"Groq API error: {e}")
    
    @property
    def model_name(self) -> str:
        """The Groq model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'groq'."""
        return "groq"
    
    @property
    def supports_files(self) -> bool:
        """Groq's Llama models are text-only."""
        return False
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Groq.
        
        Groq uses OpenAI-compatible parameters:
        - temperature: [0, 2]
        - top_p: [0, 1]
        - top_k not supported
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("Groq temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Groq top_p must be in [0, 1]")
        
        if config.top_k is not None:
            raise ValueError("Groq does not support top_k parameter")
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Groq pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model (longest first to avoid substring issues)
        pricing_key = None
        model_families = sorted(self.PRICING.keys(), key=len, reverse=True)
        
        for family in model_families:
            if family in response.model_name:
                pricing_key = family
                break
        
        if not pricing_key:
            self.logger.warning(f"Unknown Groq model for pricing: {response.model_name}")
            return 0.0
        
        pricing = self.PRICING[pricing_key]
        
        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert our Message format to OpenAI-compatible format."""
        groq_messages = []
        
        for msg in messages:
            groq_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            
            # Handle file attachments (text files only for Groq)
            if msg.attachments:
                file_contents = []
                for attachment in msg.attachments:
                    if "content" in attachment:
                        filename = attachment.get("filename", "file")
                        file_contents.append(f"\n\n--- {filename} ---\n{attachment['content']}")
                    elif "path" in attachment:
                        try:
                            with open(attachment["path"], "r", encoding="utf-8") as f:
                                content = f.read()
                                filename = attachment.get("filename", attachment["path"])
                                file_contents.append(f"\n\n--- {filename} ---\n{content}")
                        except Exception as e:
                            self.logger.error(f"Error reading attachment {attachment['path']}: {e}")
                            file_contents.append(f"\n\n[Error reading {attachment.get('filename', 'file')}: {e}]")
                
                if file_contents:
                    groq_msg["content"] = msg.content + "".join(file_contents)
            
            groq_messages.append(groq_msg)
        
        return groq_messages
    
    def _convert_response(self, groq_response) -> ModelResponse:
        """Convert Groq (OpenAI-compatible) response to our ModelResponse format."""
        choice = groq_response.choices[0]
        content = choice.message.content or ""
        
        # Extract token usage
        usage = groq_response.usage
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
            provider="groq",
        )
        cost = self.estimate_cost(temp_response)
        
        raw = groq_response.model_dump() if hasattr(groq_response, 'model_dump') else {}
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
            model_name=groq_response.model,
            provider="groq",
            finish_reason=choice.finish_reason,
            estimated_cost_usd=cost,
            raw_response=raw,
            choices=choices,
            function_call=function_call,
        )
    
    async def close(self):
        """Clean up the async client."""
        await self.client.close()