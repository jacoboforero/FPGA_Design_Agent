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


def init_llm_gateway(agent_type: str | None = None) -> Optional[object]:
    """Initialize an LLM gateway if env vars are set; otherwise return None.

    This function delegates to the adapter-level factory which supports
    per-agent environment-variable overrides (LLM_PROVIDER_{agent_type},
    LLM_MODEL_{agent_type}). The `agent_type` parameter should be a
    short, lowercase identifier such as "planner", "implementation",
    "debug", "spec_helper", "reflection" or "testbench".
    """
    # Prefer adapter-level factory which already handles per-agent overrides.
    try:
        from adapters.llm.gateway_factory import init_llm_gateway as _adapter_init  # type: ignore
        return _adapter_init(agent_type)
    except Exception:
        # Fallback to legacy behavior if adapter factory unavailable.
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
