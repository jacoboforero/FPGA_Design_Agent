

# =============================================================================
# gateway/adapters/__init__.py
"""
Model adapters for LLM Gateway.

Each adapter knows how to work with a specific model family.
"""

# Import common adapters
try:
    from .adapter_openai import OpenAIGateway
except ImportError:
    pass

try:
    from .adapter_qwen34b import Qwen34BLocalGateway
except ImportError:
    pass

# Add more as needed
# from .adapter_deepseek import DeepSeekGateway
# from .adapter_llama import LlamaGateway

__all__ = [
    "OpenAIGateway",
    "Qwen34BLocalGateway",
]