# adapter_gemini.py - Google Gemini implementation of the LLM Gateway interface

from typing import Optional, List, Dict, Any
from llm_gateway.gateway import LLMGateway, Message, MessageRole, ModelResponse, GenerationConfig
from llm_gateway.transport import TransportProtocol


class GeminiGateway(LLMGateway):
    """
    Gateway for Google Gemini models.
    
    Supports Gemini Pro, Gemini Pro Vision, and Gemini 1.5 Pro.
    
    Note: Gemini uses a significantly different format from OpenAI:
    - Messages are called "contents"
    - Roles are "user" and "model" (not "assistant")
    - System instructions are separate
    - Parameters are in "generationConfig"
    """
    
    # Pricing per million tokens (as of 2024)
    # Note: Gemini pricing varies by context length and features
    PRICING = {
        "gemini-1.5-pro": {"input": 3.50, "output": 10.50},  # Up to 128K context
        "gemini-1.5-pro-001": {"input": 3.50, "output": 10.50},
        "gemini-1.5-flash": {"input": 0.35, "output": 1.05},  # Up to 128K context
        "gemini-1.5-flash-001": {"input": 0.35, "output": 1.05},
        "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
        "gemini-pro": {"input": 0.50, "output": 1.50},  # Legacy name
    }
    
    def __init__(
        self,
        transport: TransportProtocol,
        model: str = "gemini-1.5-flash",
    ):
        """
        Initialize Gemini gateway.
        
        Args:
            transport: Transport instance (typically GoogleGeminiTransport)
            model: Gemini model identifier
        """
        self.transport = transport
        self._model = model
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Google's Gemini API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert messages to Gemini format
        system_instruction, gemini_contents = self._convert_messages(messages)
        
        # Build generation config (Gemini format)
        generation_config = {}
        if config.temperature is not None:
            generation_config["temperature"] = config.temperature
        if config.top_p is not None:
            generation_config["topP"] = config.top_p
        if config.top_k is not None:
            generation_config["topK"] = config.top_k
        if config.max_tokens is not None:
            generation_config["maxOutputTokens"] = config.max_tokens
        if config.stop_sequences:
            generation_config["stopSequences"] = config.stop_sequences
        
        # Add provider-specific parameters
        generation_config.update(config.provider_specific)
        
        # Build full request body
        request_body = {
            "contents": gemini_contents,
        }
        
        if system_instruction:
            request_body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
        
        if generation_config:
            request_body["generationConfig"] = generation_config
        
        # Make API call through transport
        gemini_response = await self.transport.call_chat_completion(
            model_id=self._model,
            messages=gemini_contents,  # Pass contents
            options=request_body,  # Full request for Gemini format
        )
        
        # Convert response to our standard format
        model_response = self._convert_response(gemini_response)
        
        return model_response
    
    @property
    def model_name(self) -> str:
        """The Gemini model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'google'."""
        return "google"
    
    @property
    def supports_files(self) -> bool:
        """Gemini Pro Vision and 1.5 support multimodal input."""
        return "vision" in self._model.lower() or "1.5" in self._model
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Google Gemini.
        
        Gemini constraints:
        - temperature: [0, 2] (but typically use [0, 1])
        - top_p: [0, 1]
        - top_k: positive integer (typically 1-40)
        - max_tokens: up to model's limit (varies by model)
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("Gemini temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Gemini top_p must be in [0, 1]")
        
        if config.top_k is not None:
            if config.top_k < 1:
                raise ValueError("Gemini top_k must be >= 1")
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Gemini pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model
        pricing_key = None
        
        # Try exact match
        for key in self.PRICING.keys():
            if key == response.model_name:
                pricing_key = key
                break
        
        # Try prefix match
        if not pricing_key:
            for key in self.PRICING.keys():
                if response.model_name.startswith(key):
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
        Convert our Message format to Gemini's format.
        
        Returns:
            (system_instruction, gemini_contents)
            
        Gemini differences:
        - Uses "contents" instead of "messages"
        - Role "assistant" becomes "model"
        - System message is separate "systemInstruction"
        - Each content has "role" and "parts" (list of content parts)
        - Parts can be text, inline_data (images), etc.
        """
        system_instruction = None
        gemini_contents = []
        
        for msg in messages:
            # Extract system message separately
            if msg.role == MessageRole.SYSTEM:
                system_instruction = msg.content
                continue
            
            # Map roles: assistant -> model
            role = "model" if msg.role == MessageRole.ASSISTANT else msg.role.value
            
            # Build content parts
            parts = [{"text": msg.content}]
            
            # Handle file attachments (text files)
            if msg.attachments:
                for attachment in msg.attachments:
                    if "content" in attachment:
                        filename = attachment.get("filename", "file")
                        parts.append({
                            "text": f"\n\n--- {filename} ---\n{attachment['content']}"
                        })
                    elif "path" in attachment:
                        try:
                            with open(attachment["path"], "r") as f:
                                file_content = f.read()
                                filename = attachment.get("filename", attachment["path"])
                                parts.append({
                                    "text": f"\n\n--- {filename} ---\n{file_content}"
                                })
                        except Exception as e:
                            parts.append({
                                "text": f"\n\n[Error reading {attachment['path']}: {e}]"
                            })
            
            gemini_content = {
                "role": role,
                "parts": parts,
            }
            
            gemini_contents.append(gemini_content)
        
        return system_instruction, gemini_contents
    
    def _convert_response(self, gemini_response: Dict[str, Any]) -> ModelResponse:
        """
        Convert Gemini response to our ModelResponse format.
        
        Gemini response structure:
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "..."}],
                        "role": "model"
                    },
                    "finishReason": "STOP",
                    "index": 0
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 123,
                "candidatesTokenCount": 456,
                "totalTokenCount": 579
            }
        }
        """
        # Extract content from first candidate
        candidates = gemini_response.get("candidates", [])
        if not candidates:
            content = ""
            finish_reason = "error"
        else:
            candidate = candidates[0]
            content_obj = candidate.get("content", {})
            parts = content_obj.get("parts", [])
            
            # Combine all text parts
            content = "".join(
                part.get("text", "") 
                for part in parts 
                if "text" in part
            )
            
            finish_reason = candidate.get("finishReason", "STOP").lower()
        
        # Extract token usage
        usage = gemini_response.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)
        total_tokens = usage.get("totalTokenCount", input_tokens + output_tokens)
        
        # Create temporary response to calculate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="google",
        )
        cost = self.estimate_cost(temp_response)
        
        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="google",
            finish_reason=finish_reason,
            estimated_cost_usd=cost,
            raw_response=gemini_response,
        )
