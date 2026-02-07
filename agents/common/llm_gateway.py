"""
LLM gateway initializer shared across agent runtimes.
Chooses provider based on env vars and returns a gateway instance or None.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

# External adapters live under adapters/llm to keep integration isolated.
try:
    from adapters.llm.gateway import Message, MessageRole, GenerationConfig  # type: ignore
    from adapters.llm.adapter_openai import OpenAIGateway  # type: ignore
    from adapters.llm.adapter_groq import GroqGateway  # type: ignore
except Exception:  # noqa: BLE001
    Message = None  # type: ignore
    MessageRole = None  # type: ignore
    GenerationConfig = None  # type: ignore
    OpenAIGateway = None  # type: ignore
    GroqGateway = None  # type: ignore

GatewayTuple = Tuple[object, object, object]


def init_llm_gateway() -> Optional[object]:
    """Initialize an LLM gateway if env vars are set; otherwise return None."""
    if os.getenv("USE_LLM") != "1":
        return None

    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "groq" and GroqGateway:
        api_key = os.getenv("GROQ_API_KEY")
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        if not api_key:
            return None
        try:
            return GroqGateway(api_key=api_key, model=model)
        except Exception:  # noqa: BLE001
            return None

    if OpenAIGateway:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if not api_key:
            return None
        try:
            return OpenAIGateway(api_key=api_key, model=model)
        except Exception:  # noqa: BLE001
            return None

    return None


__all__ = ["init_llm_gateway", "Message", "MessageRole", "GenerationConfig"]
