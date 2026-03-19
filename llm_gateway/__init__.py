# gateway/__init__.py
"""
LLM Gateway - Unified interface for multiple LLM providers.

Public API exports for easy importing:
    from gateway import LLMGateway, Message, ModelResponse
    from gateway import create_transport_by_provider
"""

# Core abstractions
from .gateway import LLMGateway, Message, MessageRole, ModelResponse, GenerationConfig, quick_generate

# Transport utilities
from .transport import TransportProtocol, TransportError, create_transport_by_provider, list_transports

__all__ = [
    # Core
    "LLMGateway",
    "Message",
    "MessageRole",
    "ModelResponse",
    "GenerationConfig",
    "quick_generate",
    # Transport
    "TransportProtocol",
    "TransportError",
    "create_transport_by_provider",
    "list_transports",
]

__version__ = "0.1.0"
