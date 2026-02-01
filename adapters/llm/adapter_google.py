"""
Google Gemini implementation of the LLM Gateway interface.

Supports Gemini 1.5 and Gemini 2.0 model families.
"""

from typing import Optional, List
import google.generativeai as genai
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)


class GoogleGeminiGateway(LLMGateway):
    """
    Gateway implementation for Google's Gemini models.
    
    Supports:
    - Gemini 2.0 (Flash, Pro)
    - Gemini 1.5 (Flash, Pro)
    - Gemini 1.0 (legacy)
    """
    
    # Pricing per million tokens (as of January 2025)
    PRICING = {
        # Gemini 2.0 family
        "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-pro": {"input": 1.25, "output": 5.00},
        
        # Gemini 1.5 family
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        
        # Gemini 1.0 (legacy)
        "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
    }
    
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
    ):
        """
        Initialize Google Gemini gateway.
        
        Args:
            api_key: Google AI Studio API key
            model: Model identifier (e.g., "gemini-2.0-flash")
        """
        genai.configure(api_key=api_key)
        self._model_name = model
        self._model = genai.GenerativeModel(model)
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Google's Gemini API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert messages to Gemini format
        gemini_messages, system_instruction = self._convert_messages(messages)
        
        # Build generation config
        generation_config = {}
        if config.temperature is not None:
            generation_config["temperature"] = config.temperature
        if config.top_p is not None:
            generation_config["top_p"] = config.top_p
        if config.top_k is not None:
            generation_config["top_k"] = config.top_k
        if config.max_tokens is not None:
            generation_config["max_output_tokens"] = config.max_tokens
        if config.stop_sequences:
            generation_config["stop_sequences"] = config.stop_sequences
        
        # Add provider-specific parameters
        generation_config.update(config.provider_specific)
        
        try:
            # Create model with system instruction if present
            if system_instruction:
                model = genai.GenerativeModel(
                    self._model_name,
                    system_instruction=system_instruction,
                )
            else:
                model = self._model
            
            # Start chat or generate
            if len(gemini_messages) > 1:
                # Multi-turn conversation
                chat = model.start_chat(history=gemini_messages[:-1])
                response = await chat.send_message_async(
                    gemini_messages[-1]["parts"],
                    generation_config=generation_config,
                )
            else:
                # Single message
                response = await model.generate_content_async(
                    gemini_messages[0]["parts"],
                    generation_config=generation_config,
                )
            
            # Convert to our standard format
            model_response = self._convert_response(response)
            
            return model_response
            
        except Exception as e:
            if "quota" in str(e).lower() or "rate" in str(e).lower():
                raise RuntimeError(f"Google Gemini rate limit exceeded: {e}")
            else:
                raise RuntimeError(f"Google Gemini API error: {e}")
    
    @property
    def model_name(self) -> str:
        """The Google Gemini model being used."""
        return self._model_name
    
    @property
    def provider(self) -> str:
        """Returns 'google'."""
        return "google"
    
    @property
    def supports_files(self) -> bool:
        """All Gemini models support multimodal input."""
        return True
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Google Gemini.
        
        Gemini constraints:
        - temperature: [0, 2]
        - top_p: [0, 1]
        - top_k: >= 1
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("Google Gemini temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Google Gemini top_p must be in [0, 1]")
        
        if config.top_k is not None:
            if config.top_k < 1:
                raise ValueError("Google Gemini top_k must be >= 1")
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on Google Gemini pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model
        pricing_key = None
        
        # Match model family (longest first)
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
    
    def _convert_messages(self, messages: List[Message]) -> tuple[List[dict], Optional[str]]:
        """
        Convert messages to Gemini format.
        
        Gemini uses:
        - system_instruction: optional system prompt
        - contents: list of parts with role/parts structure
        
        Returns:
            (gemini_messages, system_instruction)
        """
        system_instruction = None
        gemini_messages = []
        
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Accumulate system messages
                if system_instruction:
                    system_instruction += "\n\n"
                else:
                    system_instruction = ""
                system_instruction += msg.content
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
                
                # Gemini uses "user" and "model" roles
                role = "user" if msg.role == MessageRole.USER else "model"
                
                gemini_messages.append({
                    "role": role,
                    "parts": [content],
                })
        
        return gemini_messages, system_instruction
    
    def _convert_response(self, gemini_response) -> ModelResponse:
        """Convert Google Gemini response to our ModelResponse format."""
        # Extract text content
        content = gemini_response.text if hasattr(gemini_response, 'text') else ""
        
        # Extract token usage
        input_tokens = 0
        output_tokens = 0
        
        if hasattr(gemini_response, 'usage_metadata'):
            usage = gemini_response.usage_metadata
            input_tokens = getattr(usage, 'prompt_token_count', 0)
            output_tokens = getattr(usage, 'candidates_token_count', 0)
        
        total_tokens = input_tokens + output_tokens
        
        # Estimate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model_name,
            provider="google",
        )
        cost = self.estimate_cost(temp_response)
        
        # Extract finish reason
        finish_reason = "stop"
        if hasattr(gemini_response, 'candidates') and gemini_response.candidates:
            candidate = gemini_response.candidates[0]
            if hasattr(candidate, 'finish_reason'):
                finish_reason = str(candidate.finish_reason)
        
        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model_name,
            provider="google",
            finish_reason=finish_reason,
            estimated_cost_usd=cost,
            raw_response=gemini_response.to_dict() if hasattr(gemini_response, 'to_dict') else {},
        )
