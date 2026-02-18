"""
Cohere implementation of the LLM Gateway interface.

Supports Command R and Command R+ models.
"""

from typing import Optional, List
import cohere
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)


class CohereGateway(LLMGateway):
    """
    Gateway implementation for Cohere's Command models.
    
    Supports:
    - Command R+ (best performance, 128k context)
    - Command R (balanced, 128k context)
    - Command (legacy)
    """
    
    # Pricing per million tokens (as of January 2025)
    PRICING = {
        "command-r-plus": {"input": 2.50, "output": 10.00},
        "command-r": {"input": 0.15, "output": 0.60},
        "command": {"input": 1.00, "output": 2.00},
        "command-light": {"input": 0.30, "output": 0.60},
    }
    
    def __init__(
        self,
        api_key: str,
        model: str = "command-r",
    ):
        """
        Initialize Cohere gateway.
        
        Args:
            api_key: Cohere API key
            model: Model identifier (e.g., "command-r", "command-r-plus")
        """
        self.client = cohere.AsyncClient(api_key=api_key)
        self._model = model
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Cohere's Chat API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert messages to Cohere's chat history format
        cohere_messages, preamble = self._convert_messages(messages)
        
        # Build API parameters
        api_params = {
            "model": self._model,
            "chat_history": cohere_messages[:-1] if cohere_messages else [],
            "message": cohere_messages[-1]["message"] if cohere_messages else "",
        }
        
        # Add preamble (system message) if present
        if preamble:
            api_params["preamble"] = preamble
        
        # Add optional parameters
        if config.temperature is not None:
            api_params["temperature"] = config.temperature
        if config.top_p is not None:
            api_params["p"] = config.top_p  # Cohere uses 'p' instead of 'top_p'
        if config.top_k is not None:
            api_params["k"] = config.top_k  # Cohere uses 'k' instead of 'top_k'
        if config.max_tokens is not None:
            api_params["max_tokens"] = config.max_tokens
        if config.stop_sequences:
            api_params["stop_sequences"] = config.stop_sequences

        # Pass through typed generation fields (may be ignored by Cohere)
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
            response = await self.client.chat(**api_params)
            
            # Convert to our standard format
            model_response = self._convert_response(response)
            
            return model_response
            
        except cohere.TooManyRequestsError as e:
            raise RuntimeError(f"Cohere rate limit exceeded: {e}")
        except cohere.CohereError as e:
            raise RuntimeError(f"Cohere API error: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error calling Cohere: {e}")
    
    @property
    def model_name(self) -> str:
        """The Cohere model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'cohere'."""
        return "cohere"
    
    @property
    def supports_files(self) -> bool:
        """Cohere supports document upload for RAG."""
        return True
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Cohere.
        
        Cohere constraints:
        - temperature: [0, 5], typical range [0, 1]
        - p (top_p): [0, 0.99]
        - k (top_k): [0, 500]
        - max_tokens: model-specific (up to 4000 for most)
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 5:
                raise ValueError("Cohere temperature must be in [0, 5]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p < 1:
                raise ValueError("Cohere top_p must be in [0, 0.99]")
        
        if config.top_k is not None:
            if not 0 <= config.top_k <= 500:
                raise ValueError("Cohere top_k must be in [0, 500]")
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Cohere pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model
        pricing_key = None
        
        # Match model family (handle versioned models)
        model_families = sorted(self.PRICING.keys(), key=len, reverse=True)
        for family in model_families:
            if family in response.model_name.lower():
                pricing_key = family
                break
        
        if not pricing_key:
            return 0.0  # Unknown model
        
        pricing = self.PRICING[pricing_key]
        
        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _convert_messages(self, messages: List[Message]) -> tuple[List[dict], str]:
        """
        Convert messages to Cohere format.
        
        Cohere's chat API expects:
        - preamble: system message (optional)
        - chat_history: list of previous turns
        - message: current user message
        
        Returns:
            (cohere_messages, preamble)
        """
        preamble = ""
        cohere_messages = []
        
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Accumulate system messages as preamble
                if preamble:
                    preamble += "\n\n"
                preamble += msg.content
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
                
                # Cohere uses "USER" and "CHATBOT" roles (uppercase)
                role = "USER" if msg.role == MessageRole.USER else "CHATBOT"
                
                cohere_messages.append({
                    "role": role,
                    "message": content,
                })
        
        return cohere_messages, preamble
    
    def _convert_response(self, cohere_response) -> ModelResponse:
        """Convert Cohere response to our ModelResponse format."""
        content = cohere_response.text
        
        # Extract token usage (Cohere provides this in meta)
        input_tokens = 0
        output_tokens = 0
        
        if hasattr(cohere_response, 'meta') and cohere_response.meta:
            billed_units = cohere_response.meta.billed_units
            if billed_units:
                input_tokens = getattr(billed_units, 'input_tokens', 0)
                output_tokens = getattr(billed_units, 'output_tokens', 0)
        
        total_tokens = input_tokens + output_tokens
        
        # Estimate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="cohere",
        )
        cost = self.estimate_cost(temp_response)
        
        # Cohere's finish reason
        finish_reason = getattr(cohere_response, 'finish_reason', 'COMPLETE')

        raw = cohere_response.__dict__ if hasattr(cohere_response, '__dict__') else {}
        function_call = None
        choices = raw.get("choices") if isinstance(raw, dict) else None
        if isinstance(raw, dict):
            function_call = raw.get("function_call") or raw.get("tool_call")

        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="cohere",
            finish_reason=finish_reason,
            estimated_cost_usd=cost,
            raw_response=raw,
            choices=choices,
            function_call=function_call,
        )
    
    async def close(self):
        """Clean up the async client."""
        await self.client.close()
