# transport_external.py - Generic transport for external OpenAI-compatible APIs

from typing import List, Dict, Any, Optional
import httpx
from transport import TransportProtocol, TransportError


class ExternalAPITransport(TransportProtocol):
    """
    Transport for external third-party APIs using OpenAI-compatible format.
    
    Works with:
    - OpenAI (https://api.openai.com/v1)
    - Anthropic Claude (https://api.anthropic.com/v1) with adapter
    - Google Gemini (https://generativelanguage.googleapis.com/v1) with adapter
    - Azure OpenAI
    - Any OpenAI-compatible endpoint
    
    For providers that don't use OpenAI format (like Anthropic), model adapters
    should handle format conversion before calling this transport.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
        organization: Optional[str] = None,
        custom_headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize external API transport.
        
        Args:
            base_url: API base URL (e.g., "https://api.openai.com/v1")
            api_key: API authentication key
            timeout: Request timeout in seconds (default: 120)
            organization: Optional organization ID (for OpenAI)
            custom_headers: Additional headers to include in requests
        """
        self._base_url = base_url.rstrip("/")
        self._api_url = f"{self._base_url}/chat/completions"
        self._api_key = api_key
        self._timeout = timeout
        self._organization = organization
        self._custom_headers = custom_headers or {}
    
    async def call_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call external API chat completion endpoint.
        
        Args:
            model_id: Provider-specific model identifier
                     (e.g., "gpt-5", "claude-3-opus-20240229")
            messages: OpenAI-compatible message format
            options: Generation parameters in OpenAI format
                    (temperature, top_p, max_tokens, stop, etc.)
        
        Returns:
            OpenAI-compatible response dict with keys:
            - choices: [{"message": {"role", "content"}, "finish_reason"}]
            - usage: {"prompt_tokens", "completion_tokens", "total_tokens"}
            - model: str
            - id: str
            - created: int
        """
        request_data = {
            "model": model_id,
            "messages": messages,
        }
        
        if options:
            request_data.update(options)
        
        headers = self._build_headers()
        
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
                f"External API error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except httpx.RequestError as e:
            raise TransportError(
                f"External API connection error: {str(e)}"
            )
        except Exception as e:
            raise TransportError(
                f"Unexpected error calling external API: {str(e)}"
            )
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        
        headers.update(self._custom_headers)
        
        return headers
    
    @property
    def transport_name(self) -> str:
        return "external-api"
    
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
        Stream responses from external API.
        
        Yields Server-Sent Events (SSE) in OpenAI format.
        """
        request_data = {
            "model": model_id,
            "messages": messages,
            "stream": True,
        }
        
        if options:
            request_data.update(options)
        
        headers = self._build_headers()
        
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
                f"External API streaming error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except Exception as e:
            raise TransportError(
                f"Unexpected streaming error: {str(e)}"
            )


class OpenAITransport(ExternalAPITransport):
    """Convenience subclass for OpenAI API with sensible defaults."""
    
    def __init__(
        self,
        api_key: str,
        organization: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ):
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            organization=organization,
        )
    
    @property
    def transport_name(self) -> str:
        return "openai"


class AnthropicTransport(ExternalAPITransport):
    """
    Transport for Anthropic Claude API.
    
    Note: Anthropic uses a different message format than OpenAI.
    Model adapters should convert to Anthropic format before calling.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 120.0,
        anthropic_version: str = "2023-06-01",
    ):
        custom_headers = {
            "anthropic-version": anthropic_version,
        }
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            custom_headers=custom_headers,
        )
    
    def _build_headers(self) -> Dict[str, str]:
        """Anthropic uses x-api-key instead of Bearer token."""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
        }
        headers.update(self._custom_headers)
        return headers
    
    @property
    def transport_name(self) -> str:
        return "anthropic"
    
    async def call_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Anthropic uses /messages endpoint, not /chat/completions.
        Override the API URL.
        """
        original_url = self._api_url
        self._api_url = f"{self._base_url}/messages"
        
        try:
            return await super().call_chat_completion(model_id, messages, options)
        finally:
            self._api_url = original_url


class GoogleGeminiTransport(ExternalAPITransport):
    """
    Transport for Google Gemini API.
    
    Note: Gemini uses a different format. Model adapters should convert.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 120.0,
    ):
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
    
    def _build_headers(self) -> Dict[str, str]:
        """Gemini uses query parameter for API key."""
        return {
            "Content-Type": "application/json",
        }
    
    async def call_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Gemini uses different endpoint structure with API key in query."""
        # Gemini format: POST /v1beta/models/{model}:generateContent?key={api_key}
        api_url = f"{self._base_url}/models/{model_id}:generateContent"
        
        request_data = {
            "contents": messages,  # Gemini format
        }
        
        if options:
            request_data["generationConfig"] = options
        
        headers = self._build_headers()
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    api_url,
                    json=request_data,
                    headers=headers,
                    params={"key": self._api_key},
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            raise TransportError(
                f"Gemini API error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
        except Exception as e:
            raise TransportError(f"Error calling Gemini: {str(e)}")
    
    @property
    def transport_name(self) -> str:
        return "google-gemini"
