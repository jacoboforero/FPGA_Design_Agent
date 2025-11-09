# transport_ollama.py - Ollama API transport implementation

from typing import List, Dict, Any, Optional
import httpx
from transport import TransportProtocol, TransportError


class OllamaTransport(TransportProtocol):
    """
    Transport for Ollama-hosted local models.
    
    Ollama provides a local server that hosts various open-source models
    (Llama, Qwen, DeepSeek, Mistral, etc.) with a consistent API.
    
    API Documentation: https://github.com/ollama/ollama/blob/main/docs/api.md
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = 300.0,
    ):
        """
        Initialize Ollama transport.
        
        Args:
            base_url: Ollama server URL (default: http://localhost:11434)
            timeout: Request timeout in seconds (default: 300)
        """
        self._base_url = base_url.rstrip("/")
        self._api_url = f"{self._base_url}/api/chat"
        self._timeout = timeout
    
    async def call_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call Ollama's chat completion endpoint.
        
        Args:
            model_id: Ollama model name (e.g., "qwen3:4b", "deepseek-coder:6.7b")
            messages: OpenAI-compatible message format
            options: Ollama-specific options (temperature, top_p, top_k, 
                    num_predict, stop, etc.)
        
        Returns:
            Ollama response dict with keys:
            - message: {role, content}
            - done: bool
            - done_reason: str
            - prompt_eval_count: int (input tokens)
            - eval_count: int (output tokens)
        """
        request_data = {
            "model": model_id,
            "messages": messages,
            "stream": False,
        }
        
        if options:
            request_data["options"] = options
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._api_url, json=request_data)
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            raise TransportError(
                f"Ollama API error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except httpx.RequestError as e:
            raise TransportError(
                f"Ollama connection error: {str(e)}"
            )
        except Exception as e:
            raise TransportError(
                f"Unexpected error calling Ollama: {str(e)}"
            )
    
    @property
    def transport_name(self) -> str:
        return "ollama"
    
    @property
    def supports_streaming(self) -> bool:
        return True
    
    async def call_streaming(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ):
        """
        Stream responses from Ollama.
        
        Yields JSON objects with 'message' and 'done' fields.
        """
        request_data = {
            "model": model_id,
            "messages": messages,
            "stream": True,
        }
        
        if options:
            request_data["options"] = options
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", self._api_url, json=request_data
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            import json
                            yield json.loads(line)
                            
        except httpx.HTTPStatusError as e:
            raise TransportError(
                f"Ollama streaming error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except Exception as e:
            raise TransportError(
                f"Unexpected streaming error: {str(e)}"
            )
