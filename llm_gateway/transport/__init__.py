


# =============================================================================
# gateway/transport/__init__.py
"""
Transport layer for LLM Gateway.

Handles communication protocols with different LLM hosting services.
"""

from .base import TransportProtocol, TransportError
from .registry import (
    get_transport_registry,
    create_transport_by_provider,
    create_transport,
    list_transports,
)

# Optional: Auto-import all transports for immediate availability
# (Only do this if you want ALL transports loaded at import time)
try:
    from .transport_ollama import OllamaTransport
    from .transport_huggingface import HuggingFaceTransport
    from .transport_external import (
        ExternalAPITransport,
        OpenAITransport,
        AnthropicTransport,
        GoogleGeminiTransport,
    )
except ImportError:
    # Some transports may have optional dependencies
    pass

__all__ = [
    "TransportProtocol",
    "TransportError",
    "get_transport_registry",
    "create_transport_by_provider",
    "create_transport",
    "list_transports",
]
