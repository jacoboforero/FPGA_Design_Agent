# transport_huggingface.py - HuggingFace TGI/vLLM transport implementation

from typing import List, Dict, Any, Optional
import httpx
from transport import TransportProtocol, TransportError


class HuggingFaceTransport(TransportProtocol):
    """
    Transport for HuggingFace Text Generation Inference (TGI) servers.
    
    Also compatible with vLLM servers that use OpenAI-compatible endpoints.
    HuggingFace TGI provides local hosting for HuggingFace Hub models.
    
    API Documentation: 
    - TGI: https://huggingface.co/docs/text-generation-inference
    - vLLM: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 300.0,
        api_key: Optional[str] = None,
    ):
        """
        Initialize HuggingFace transport.
        
        Args:
            base_url: TGI/vLLM server URL (default: http://localhost:8080)
            timeout: Request timeout in seconds (default: 300)
            api_key: Optional API key for authentication
        """
        self._base_url = base_url.rstrip("/")
        self._api_url = f"{self._base_url}/v1/chat/completions"
        self._timeout = timeout
        self._api_key = api_key
    
    async def call_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call HuggingFace TGI chat completion endpoint.
        
        Args:
            model_id: Model identifier (often the HuggingFace Hub path,
                     e.g., "meta-llama/Llama-3-8b-instruct")
            messages: OpenAI-compatible message format
            options: Generation parameters (temperature, top_p, max_tokens, etc.)
                    Note: HuggingFace uses flat structure, not nested "options"
        
        Returns:
            OpenAI-compatible response dict with keys:
            - choices: [{"message": {"role", "content"}, "finish_reason"}]
            - usage: {"prompt_tokens", "completion_tokens", "total_tokens"}
            - model: str
        """
        request_data = {
            "model": model_id,
            "messages": messages,
        }
        
        # HuggingFace TGI uses flat parameter structure (like OpenAI)
        if options:
            # Map common option names to TGI equivalents
            mapped_options = self._map_options(options)
            request_data.update(mapped_options)
        
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._api_url,
                    json=request_data,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            raise TransportError(
                f"HuggingFace API error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except httpx.RequestError as e:
            raise TransportError(
                f"HuggingFace connection error: {str(e)}"
            )
        except Exception as e:
            raise TransportError(
                f"Unexpected error calling HuggingFace: {str(e)}"
            )
    
    def _map_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Ollama-style options to HuggingFace TGI parameter names.
        
        Common mappings:
        - num_predict -> max_tokens
        - stop -> stop (same)
        - Other params generally align with OpenAI format
        """
        mapped = {}
        
        # Direct mappings
        if "temperature" in options:
            mapped["temperature"] = options["temperature"]
        if "top_p" in options:
            mapped["top_p"] = options["top_p"]
        if "top_k" in options:
            mapped["top_k"] = options["top_k"]
        if "stop" in options:
            mapped["stop"] = options["stop"]
        
        # Handle different naming conventions
        if "num_predict" in options:
            mapped["max_tokens"] = options["num_predict"]
        elif "max_tokens" in options:
            mapped["max_tokens"] = options["max_tokens"]
        
        # Pass through any unrecognized options
        for key, value in options.items():
            if key not in mapped and key not in ["num_predict"]:
                mapped[key] = value
        
        return mapped
    
    @property
    def transport_name(self) -> str:
        return "huggingface"
    
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
        Stream responses from HuggingFace TGI.
        
        Yields Server-Sent Events (SSE) in OpenAI format.
        """
        request_data = {
            "model": model_id,
            "messages": messages,
            "stream": True,
        }
        
        if options:
            mapped_options = self._map_options(options)
            request_data.update(mapped_options)
        
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    self._api_url,
                    json=request_data,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            if data.strip() == "[DONE]":
                                break
                            import json
                            yield json.loads(data)
                            
        except httpx.HTTPStatusError as e:
            raise TransportError(
                f"HuggingFace streaming error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except Exception as e:
            raise TransportError(
                f"Unexpected streaming error: {str(e)}"
            )
