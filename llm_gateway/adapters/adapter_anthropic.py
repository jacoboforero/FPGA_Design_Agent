# adapter_anthropic.py - Anthropic Claude implementation of the LLM Gateway interface

from typing import Optional, List, Dict, Any
from llm_gateway.gateway import LLMGateway, Message, MessageRole, ModelResponse, GenerationConfig
from llm_gateway.transport import TransportProtocol


class AnthropicGateway(LLMGateway):
    """
    Gateway for Anthropic Claude models.
    
    Supports Claude 3 family (Opus, Sonnet, Haiku) and Claude 3.5.
    
    Note: Anthropic uses a different message format than OpenAI:
    - System messages are separate (not in messages array)
    - Uses "max_tokens" (required) instead of optional
    - Different parameter names (e.g., "top_k" instead of OpenAI's non-existent one)
    """
    
    # Pricing per million tokens (as of 2024)
    PRICING = {
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet-20240620": {"input": 3.00, "output": 15.00},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }
    
    def __init__(
        self,
        transport: TransportProtocol,
        model: str = "claude-3-5-sonnet-20241022",
    ):
        """
        Initialize Anthropic gateway.
        
        Args:
            transport: Transport instance (typically AnthropicTransport)
            model: Claude model identifier
        """
        self.transport = transport
        self._model = model
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Anthropic's Claude API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Anthropic requires max_tokens
        if config.max_tokens is None:
            config.max_tokens = 4096  # Default to 4K tokens
        
        # Convert messages to Anthropic format
        system_prompt, anthropic_messages = self._convert_messages(messages)
        
        # Build request body (Anthropic format)
        request_body = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": config.max_tokens,
        }
        
        # Add system prompt if present
        if system_prompt:
            request_body["system"] = system_prompt
        
        # Add optional parameters
        if config.temperature is not None:
            request_body["temperature"] = config.temperature
        if config.top_p is not None:
            request_body["top_p"] = config.top_p
        if config.top_k is not None:
            request_body["top_k"] = config.top_k
        if config.stop_sequences:
            request_body["stop_sequences"] = config.stop_sequences
        
        # Add provider-specific parameters
        request_body.update(config.provider_specific)
        
        # Make API call through transport
        # Note: We pass the full request as "options" since Anthropic format differs
        anthropic_response = await self.transport.call_chat_completion(
            model_id=self._model,
            messages=anthropic_messages,
            options=request_body,
        )
        
        # Convert response to our standard format
        model_response = self._convert_response(anthropic_response)
        
        return model_response
    
    @property
    def model_name(self) -> str:
        """The Claude model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'anthropic'."""
        return "anthropic"
    
    @property
    def supports_files(self) -> bool:
        """Claude 3 supports vision and file content."""
        return True
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Anthropic Claude.
        
        Anthropic constraints:
        - temperature: [0, 1]
        - top_p: [0, 1]
        - top_k: [1, 500] (only for Claude 3+)
        - max_tokens: required, up to model's limit
        - Can use temperature OR top_p (not both recommended)
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 1:
                raise ValueError("Anthropic temperature must be in [0, 1]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Anthropic top_p must be in [0, 1]")
        
        if config.top_k is not None:
            if not 1 <= config.top_k <= 500:
                raise ValueError("Anthropic top_k must be in [1, 500]")
        
        if config.temperature is not None and config.top_p is not None:
            # Anthropic recommends using one or the other
            pass  # Allow it but could log a warning
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Anthropic pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model
        pricing_key = None
        for key in self.PRICING.keys():
            if key == response.model_name:
                pricing_key = key
                break
        
        if not pricing_key:
            # Try to match by family (e.g., "claude-3-opus")
            for key in self.PRICING.keys():
                if key.rsplit("-", 1)[0] in response.model_name:
                    pricing_key = key
                    break
        
        if not pricing_key:
            return 0.0  # Unknown model
        
        pricing = self.PRICING[pricing_key]
        
        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _convert_messages(self, messages: List[Message]) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """
        Convert our Message format to Anthropic's format.
        
        Returns:
            (system_prompt, anthropic_messages)
            
        Anthropic differences:
        - System message is separate, not in messages array
        - Messages must alternate user/assistant
        - Each message has "role" and "content"
        - Content can be string or list of content blocks for multimodal
        """
        system_prompt = None
        anthropic_messages = []
        
        for msg in messages:
            # Extract system message separately
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
                continue
            
            # Build message content
            content = msg.content
            
            # Handle file attachments
            if msg.attachments:
                # For text files, append to content as text
                # For images, would need to convert to base64 content blocks
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
                    content = msg.content + "".join(file_contents)
            
            anthropic_msg = {
                "role": msg.role.value,
                "content": content,
            }
            
            anthropic_messages.append(anthropic_msg)
        
        return system_prompt, anthropic_messages
    
    def _convert_response(self, anthropic_response: Dict[str, Any]) -> ModelResponse:
        """
        Convert Anthropic response to our ModelResponse format.
        
        Anthropic response structure:
        {
            "id": "msg_...",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "..."}],
            "model": "claude-3-5-sonnet-20241022",
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 123,
                "output_tokens": 456
            }
        }
        """
        # Extract content from content blocks
        content_blocks = anthropic_response.get("content", [])
        if isinstance(content_blocks, list):
            # Combine all text blocks
            content = "".join(
                block.get("text", "") 
                for block in content_blocks 
                if block.get("type") == "text"
            )
        else:
            content = str(content_blocks)
        
        # Extract token usage
        usage = anthropic_response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = input_tokens + output_tokens
        
        # Create temporary response to calculate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=anthropic_response.get("model", self._model),
            provider="anthropic",
        )
        cost = self.estimate_cost(temp_response)
        
        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=anthropic_response.get("model", self._model),
            provider="anthropic",
            finish_reason=anthropic_response.get("stop_reason"),
            estimated_cost_usd=cost,
            raw_response=anthropic_response,
        )
