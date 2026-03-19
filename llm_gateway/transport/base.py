# transport.py - Base abstraction for LLM API transport mechanisms

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class TransportProtocol(ABC):
    """
    Abstract base for transport protocols that handle HTTP/API communication.
    
    Transport protocols are responsible for:
    - Managing connections to LLM hosting services
    - Converting standardized requests to provider-specific API formats
    - Returning raw provider responses for model adapters to parse
    
    Each transport implementation should be a separate file (e.g., transport_ollama.py)
    for better modularity and easier extension.
    """
    
    @abstractmethod
    async def call_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make a chat completion API call.
        
        Args:
            model_id: Provider-specific model identifier
                     (e.g., "qwen3:4b" for Ollama, "gpt-5" for OpenAI)
            messages: List of message dicts with 'role' and 'content' keys
                     in OpenAI-compatible format
            options: Provider-specific generation parameters
                    (temperature, top_p, max_tokens, etc.)
        
        Returns:
            Raw response dict from the provider's API
            
        Raises:
            TransportError: If the API call fails
        """
        pass
    
    @property
    @abstractmethod
    def transport_name(self) -> str:
        """
        Identifier for this transport (e.g., "ollama", "huggingface", "openai").
        Used for logging and debugging.
        """
        pass
    
    @property
    def supports_streaming(self) -> bool:
        """
        Whether this transport supports streaming responses.
        Override if streaming is supported.
        """
        return False
    
    async def call_streaming(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ):
        """
        Stream chat completion responses.
        
        Override this method if streaming is supported.
        Should yield response chunks.
        
        Raises:
            NotImplementedError: If streaming is not supported
        """
        raise NotImplementedError(
            f"{self.transport_name} does not support streaming"
        )


class TransportError(Exception):
    """Raised when a transport operation fails."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
