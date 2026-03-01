"""
LLM gateway initializer shared across agent runtimes.
Chooses provider based on env vars and returns a gateway instance or None.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple
from core.runtime.config import get_runtime_config

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


def init_llm_gateway(
    *,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> Optional[object]:
    """Initialize an LLM gateway from runtime config + secret env vars."""
    llm_cfg = get_runtime_config().llm
    if not llm_cfg.enabled:
        return None

    provider = (provider_override or llm_cfg.provider or "openai").lower()
    if provider == "groq" and GroqGateway:
        api_key = os.getenv("GROQ_API_KEY")
        model = model_override or llm_cfg.default_model or "llama-3.1-8b-instant"
        if not api_key:
            return None
        try:
            return GroqGateway(api_key=api_key, model=model)
        except Exception:  # noqa: BLE001
            return None

    if OpenAIGateway:
        api_key = os.getenv("OPENAI_API_KEY")
        model = model_override or llm_cfg.default_model or "gpt-4.1-mini"
        if not api_key:
            return None
        try:
            return OpenAIGateway(api_key=api_key, model=model)
        except Exception:  # noqa: BLE001
            return None

    return None


__all__ = ["init_llm_gateway", "Message", "MessageRole", "GenerationConfig"]
