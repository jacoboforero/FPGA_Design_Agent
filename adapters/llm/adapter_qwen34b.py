"""
Qwen3 4B implementation of the LLM Gateway interface.

Handles local Qwen3:4b model calls through Ollama.
"""

from typing import Optional, List
import httpx
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    ModelResponse,
    GenerationConfig,
)


class Qwen34BLocalGateway(LLMGateway):
    """
    Gateway implementation for Qwen3:4b running locally via Ollama.
    
    Model specifics:
    - 4B parameters
    - 32K context window
    - Optimized for code generation and reasoning tasks
    """
    
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        """
        Initialize Qwen3:4b gateway.
        
        Args:
            ollama_base_url: Ollama API base URL (default: http://localhost:11434)
        """
        self._model = "qwen3:4b"
        self._base_url = ollama_base_url.rstrip("/")
        self._api_url = f"{self._base_url}/api/chat"
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using Qwen3:4b through Ollama."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert our Message format to Ollama's format
        ollama_messages = self._convert_messages(messages)
        
        # Build API request
        request_data = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
        }
        
        # Add optional parameters
        options = {}
        if config.temperature is not None:
            options["temperature"] = config.temperature
        if config.top_p is not None:
            options["top_p"] = config.top_p
        if config.top_k is not None:
            options["top_k"] = config.top_k
        if config.stop_sequences:
            options["stop"] = config.stop_sequences
        if config.max_tokens is not None:
            options["num_predict"] = config.max_tokens
        
        # Add provider-specific options
        options.update(config.provider_specific)
        
        if options:
            request_data["options"] = options
        
        # Make API call
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(self._api_url, json=request_data)
            response.raise_for_status()
            ollama_response = response.json()
        
        # Convert to our standard format
        model_response = self._convert_response(ollama_response)
        
        return model_response
    
    @property
    def model_name(self) -> str:
        """Returns 'qwen3:4b'."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'qwen3-local'."""
        return "qwen3-local"
    
    @property
    def supports_files(self) -> bool:
        """Qwen3:4b supports text and file content."""
        return True
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for Qwen3:4b.
        
        Qwen3:4b constraints:
        - temperature: [0, 2], works best in [0.6, 0.9]
        - top_p: [0, 1]
        - top_k: positive integer
        - max_tokens: up to 32K context window
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("Qwen3:4b temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("Qwen3:4b top_p must be in [0, 1]")
        
        if config.top_k is not None:
            if config.top_k < 1:
                raise ValueError("Qwen3:4b top_k must be >= 1")
        
        if config.max_tokens is not None:
            if config.max_tokens > 32000:
                raise ValueError("Qwen3:4b supports up to 32K tokens")
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """Local model has no API cost."""
        return 0.0
    
    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert our Message format to Ollama's format."""
        ollama_messages = []
        
        for msg in messages:
            ollama_msg = {
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
                    ollama_msg["content"] = msg.content + "".join(file_contents)
            
            ollama_messages.append(ollama_msg)
        
        return ollama_messages
    
    def _convert_response(self, ollama_response: dict) -> ModelResponse:
        """Convert Ollama response to our ModelResponse format."""
        # Extract content from the message
        message = ollama_response.get("message", {})
        content = message.get("content", "")
        
        # Extract token usage
        prompt_tokens = ollama_response.get("prompt_eval_count", 0)
        completion_tokens = ollama_response.get("eval_count", 0)
        total_tokens = prompt_tokens + completion_tokens
        
        # Extract finish reason
        finish_reason = ollama_response.get("done_reason", "stop")
        
        return ModelResponse(
            content=content,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=0.0,
            model_name=self._model,
            provider="qwen3-local",
            finish_reason=finish_reason,
            raw_response=ollama_response,
        )
