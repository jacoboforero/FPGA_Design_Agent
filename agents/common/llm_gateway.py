"""
LLM gateway initializer shared across agent runtimes.

Runtime YAML is the source of truth for provider/model selection.
Environment variables are used for provider credentials and compatibility
fallbacks only.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from core.runtime.config import get_runtime_config

# External adapters live under adapters/llm to keep integration isolated.
try:
    from adapters.llm.gateway import Message, MessageRole, GenerationConfig  # type: ignore
except Exception:  # noqa: BLE001
    Message = None  # type: ignore
    MessageRole = None  # type: ignore
    GenerationConfig = None  # type: ignore

GatewayTuple = Tuple[object, object, object]

_DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "groq": "llama-3.1-8b-instant",
    "anthropic": "claude-sonnet-4-5-20250929",
    "google": "gemini-2.0-flash",
    "cohere": "command-r",
    "grok": "grok-2-mini",
    "qwen-local": "qwen3:4b",
}

_PROVIDER_ALIASES = {
    "qwen": "qwen-local",
    "ollama": "qwen-local",
    "local": "qwen-local",
}


def _clean_optional(value: Optional[str], *, lower: bool = False) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned.lower() if lower else cleaned


def _normalize_agent_type(agent_type: Optional[str]) -> Optional[str]:
    cleaned = _clean_optional(agent_type, lower=True)
    if not cleaned:
        return None
    return cleaned.replace("-", "_")


def _resolve_provider_and_model(
    agent_type: Optional[str],
    provider_override: Optional[str],
    model_override: Optional[str],
) -> tuple[str, str]:
    llm_cfg = get_runtime_config().llm

    provider = _clean_optional(provider_override, lower=True)
    model = _clean_optional(model_override)

    agent_key = _normalize_agent_type(agent_type)
    overrides = getattr(llm_cfg, "agent_overrides", {}) or {}
    if agent_key and isinstance(overrides, dict):
        override = overrides.get(agent_key)
        if override is None:
            override = overrides.get(agent_key.replace("_", "-"))
        if override is not None:
            if not provider:
                provider = _clean_optional(getattr(override, "provider", None), lower=True)
            if not model:
                model = _clean_optional(getattr(override, "model", None))

    # Backward compatibility with existing main behavior.
    if not model and agent_key == "spec_helper":
        model = _clean_optional(getattr(llm_cfg, "spec_helper_model", None))

    provider = provider or _clean_optional(getattr(llm_cfg, "provider", None), lower=True) or "openai"
    provider = _PROVIDER_ALIASES.get(provider, provider)

    model = model or _clean_optional(getattr(llm_cfg, "default_model", None)) or _DEFAULT_MODELS.get(provider, "gpt-4.1-mini")

    return provider, model


def init_llm_gateway(
    agent_type: str | None = None,
    *,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> Optional[object]:
    """Initialize an LLM gateway from runtime YAML + secret env vars."""
    llm_cfg = get_runtime_config().llm
    if not llm_cfg.enabled:
        return None

    provider, model = _resolve_provider_and_model(
        agent_type=agent_type,
        provider_override=provider_override,
        model_override=model_override,
    )

    try:
        if provider == "openai":
            from adapters.llm.adapter_openai import OpenAIGateway  # type: ignore

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None
            return OpenAIGateway(api_key=api_key, model=model)

        if provider == "groq":
            from adapters.llm.adapter_groq import GroqGateway  # type: ignore

            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                return None
            return GroqGateway(api_key=api_key, model=model)

        if provider == "anthropic":
            from adapters.llm.adapter_anthropic import AnthropicGateway  # type: ignore

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return None
            return AnthropicGateway(api_key=api_key, model=model)

        if provider == "google":
            from adapters.llm.adapter_google import GoogleGeminiGateway  # type: ignore

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return None
            return GoogleGeminiGateway(api_key=api_key, model=model)

        if provider == "cohere":
            from adapters.llm.adapter_cohere import CohereGateway  # type: ignore

            api_key = os.getenv("COHERE_API_KEY")
            if not api_key:
                return None
            return CohereGateway(api_key=api_key, model=model)

        if provider == "grok":
            from adapters.llm.adapter_grok import GrokGateway  # type: ignore

            api_key = os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY")
            if not api_key:
                return None
            return GrokGateway(api_key=api_key, model=model)

        if provider == "qwen-local":
            from adapters.llm.adapter_qwen import QwenLocalGateway  # type: ignore

            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return QwenLocalGateway(model=model, ollama_base_url=ollama_url)

        return None
    except Exception:  # noqa: BLE001
        return None


__all__ = ["init_llm_gateway", "Message", "MessageRole", "GenerationConfig"]
