# OpenAI implementation of the LLM Gateway interface.

from typing import Optional, List
from openai import AsyncOpenAI
from gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)

class OpenAIGateway(LLMGateway):
    
    # Pricing must currently be manually maintained. Price per million tokens.
    PRICING = {
        # Very-High-Cost Model "gpt-5-pro": {"input": 15.00, "output": 120.00},
        "gpt-5": {"input": 1.25, "output": 10.00},
        "gpt-5-mini": {"input": 0.25, "output": 2.00},
        "gpt-5-nano": {"input": 0.05, "output": 0.40},
        "gpt-4.1": {"input": 2.00, "output": 8.00},
        "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        # LEGACY "gpt-3.5-turbo": {"input": 0.5, "output": 1.5}
    }
    

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5-nano",
        organization: Optional[str] = None, # Required for billing, rate limits, usage reports.
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            organization=organization,
        )
        self._model = model
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using OpenAI's chat completion API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert our Message format to OpenAI's format
        openai_messages = self._convert_messages(messages)
        
        # Build API parameters
        api_params = {
            "model": self._model,
            "messages": openai_messages,
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
        
        # Add provider-specific parameters
        api_params.update(config.provider_specific)
        
        # Make API call
        response = await self.client.chat.completions.create(**api_params)
        
        # Convert to our standard format
        model_response = self._convert_response(response)
        
        return model_response
    
    @property
    def model_name(self) -> str:
        """The OpenAI model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'openai'."""
        return "openai"
    
    @property
    def supports_files(self) -> bool:
        """OpenAI supports vision/files for GPT-4 vision models."""
        return "vision" in self._model or "gpt-4o" in self._model
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for OpenAI.
        
        OpenAI constraints:
        - temperature: [0, 2]
        - top_p: [0, 1]
        - Can use both temperature and top_p (OpenAI recommends altering one, not both)
        - top_k not supported
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("OpenAI temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("OpenAI top_p must be in [0, 1]")
        
        if config.top_k is not None:
            raise ValueError("OpenAI does not support top_k parameter")
        
        if config.temperature is not None and config.top_p is not None:
            # Warning: OpenAI docs recommend not using both
            pass  # Allow it but could log a warning
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on OpenAI pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model (handle versioned models)
        pricing_key = None
        for key in self.PRICING.keys():
            if key in response.model_name:
                pricing_key = key
                break
        
        if not pricing_key:
            return 0.0  # Unknown model, can't estimate
        
        pricing = self.PRICING[pricing_key]
        
        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert our Message format to OpenAI's format."""
        openai_messages = []
        
        for msg in messages:
            openai_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            
            # Handle file attachments - append their text content to the message
            if msg.attachments:
                file_contents = []
                for attachment in msg.attachments:
                    if "content" in attachment:
                        # File content provided directly
                        filename = attachment.get("filename", "file")
                        file_contents.append(f"\n\n--- {filename} ---\n{attachment['content']}")
                    elif "path" in attachment:
                        # File path provided - read it
                        try:
                            with open(attachment["path"], "r") as f:
                                content = f.read()
                                filename = attachment.get("filename", attachment["path"])
                                file_contents.append(f"\n\n--- {filename} ---\n{content}")
                        except Exception as e:
                            file_contents.append(f"\n\n[Error reading {attachment['path']}: {e}]")
                
                # Append all file contents to the message content
                if file_contents:
                    openai_msg["content"] = msg.content + "".join(file_contents)
            
            openai_messages.append(openai_msg)
        
        return openai_messages
    
    def _convert_response(self, openai_response) -> ModelResponse:
        """Convert OpenAI response to our ModelResponse format."""
        choice = openai_response.choices[0]
        content = choice.message.content or ""
        
        # Extract token usage
        usage = openai_response.usage
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
            provider="openai",
        )
        cost = self.estimate_cost(temp_response)
        
        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=openai_response.model,
            provider="openai",
            finish_reason=choice.finish_reason,
            estimated_cost_usd=cost,
            raw_response=openai_response.model_dump(),
        )