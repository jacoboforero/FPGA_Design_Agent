"""OpenAI implementation of the LLM Gateway interface.

Supports both Chat Completions and Responses APIs.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    ModelResponse,
    GenerationConfig,
)
from core.runtime.config import get_runtime_config
from core.runtime.llm_rate_control import get_llm_rate_controller


class OpenAIGateway(LLMGateway):

    # Pricing must currently be manually maintained. Price per million tokens.
    PRICING = {
        # Very-High-Cost Model "gpt-5-pro": {"input": 15.00, "output": 120.00},
        "gpt-5": {"input": 1.25, "output": 10.00},
        "gpt-5-mini": {"input": 0.25, "output": 2.00},
        "gpt-5-nano": {"input": 0.05, "output": 0.40},
        "gpt-4.1": {"input": 2.00, "output": 8.00},
        "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
        # LEGACY "gpt-3.5-turbo": {"input": 0.5, "output": 1.5}
    }
    _VALID_API_MODES = {"auto", "chat", "responses"}

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5-nano",
        organization: Optional[str] = None, # Required for billing, rate limits, usage reports.
    ):
        try:
            request_timeout_s = float(get_runtime_config().llm.request_timeout_s)
        except Exception:
            request_timeout_s = 120.0
        self.client = AsyncOpenAI(
            api_key=api_key,
            organization=organization,
            timeout=request_timeout_s,
        )
        self._model = model
        raw_mode = os.getenv("OPENAI_API_MODE", "auto").strip().lower() or "auto"
        if raw_mode == "response":
            raw_mode = "responses"
        self._api_mode = raw_mode if raw_mode in self._VALID_API_MODES else "auto"

    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using OpenAI's chat completion or responses API."""
        controller = get_llm_rate_controller()
        ticket = controller.acquire()
        error: Exception | None = None
        try:
            config = config or GenerationConfig()
            config = self.validate_config(config)

            mode = self._resolve_api_mode(config)
            if mode == "responses":
                response = await self.client.responses.create(**self._build_responses_params(messages, config))
                return self._convert_responses_response(response)

            # Chat mode, with fallback to Responses for model/API compatibility errors.
            try:
                response = await self.client.chat.completions.create(**self._build_chat_params(messages, config))
                return self._convert_chat_response(response)
            except Exception as exc:  # noqa: BLE001
                if not self._should_fallback_to_responses(exc):
                    raise
                response = await self.client.responses.create(**self._build_responses_params(messages, config))
                return self._convert_responses_response(response)
        except Exception as exc:  # noqa: BLE001
            error = exc
            raise
        finally:
            controller.release(ticket, error=error)
    
    @property
    def model_name(self) -> str:
        """The OpenAI model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'openai'."""
        return "openai"
    
    @property
    def supports_files(self) -> bool:
        """OpenAI supports vision/files for GPT-4 vision models."""
        return "vision" in self._model or "gpt-4o" in self._model

    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for OpenAI.
        
        OpenAI constraints:
        - temperature: [0, 2]
        - top_p: [0, 1]
        - Can use both temperature and top_p (OpenAI recommends altering one, not both)
        - top_k not supported
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("OpenAI temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("OpenAI top_p must be in [0, 1]")
        
        if config.top_k is not None:
            raise ValueError("OpenAI does not support top_k parameter")
        
        if config.temperature is not None and config.top_p is not None:
            # Warning: OpenAI docs recommend not using both
            pass  # Allow it but could log a warning

        return config

    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on OpenAI pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model (handle versioned models)
        pricing_key = None
        for key in self.PRICING.keys():
            if key in response.model_name:
                pricing_key = key
                break
        
        if not pricing_key:
            return 0.0  # Unknown model, can't estimate

        pricing = self.PRICING[pricing_key]

        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost

    def _resolve_api_mode(self, config: GenerationConfig) -> str:
        mode = self._api_mode
        if mode not in self._VALID_API_MODES:
            mode = "auto"
        if mode in ("responses", "chat"):
            if mode == "chat" and self._is_responses_only_model():
                return "responses"
            return mode
        # auto mode
        if self._is_responses_only_model():
            return "responses"
        if self._is_reasoning_model():
            return "responses"
        return "chat"

    def _is_reasoning_model(self) -> bool:
        model = self._model.lower()
        return model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3") or model.startswith("o4")

    def _is_responses_only_model(self) -> bool:
        model = self._model.lower()
        # Certain high-end snapshots are Responses-first/only in docs.
        return model.startswith("gpt-5-pro") or model.startswith("gpt-5.2-pro")

    def _sampling_allowed_for_model(self, provider_specific: Dict[str, Any]) -> bool:
        model = self._model.lower()
        if not model.startswith("gpt-5"):
            return True

        # GPT-5.1/GPT-5.2 only support sampling params when reasoning effort is none.
        effort = None
        if isinstance(provider_specific.get("reasoning"), dict):
            effort = provider_specific["reasoning"].get("effort")
        if effort is None:
            effort = provider_specific.get("reasoning_effort")
        if effort is not None:
            effort = str(effort).strip().lower()
        is_51_or_newer = model.startswith("gpt-5.1") or model.startswith("gpt-5.2")
        return bool(is_51_or_newer and effort == "none")

    def _build_chat_params(self, messages: List[Message], config: GenerationConfig) -> Dict[str, Any]:
        provider_specific = dict(config.provider_specific or {})
        reasoning_cfg = provider_specific.pop("reasoning", None)
        if "reasoning_effort" not in provider_specific and isinstance(reasoning_cfg, dict):
            effort = reasoning_cfg.get("effort")
            if effort is not None:
                provider_specific["reasoning_effort"] = effort

        params: Dict[str, Any] = {
            "model": self._model,
            "messages": self._convert_messages(messages),
        }

        sampling_allowed = self._sampling_allowed_for_model(provider_specific)
        if sampling_allowed:
            if config.temperature is not None:
                params["temperature"] = config.temperature
            if config.top_p is not None:
                params["top_p"] = config.top_p
        else:
            provider_specific.pop("temperature", None)
            provider_specific.pop("top_p", None)
            provider_specific.pop("logprobs", None)

        if config.max_tokens is not None:
            # max_tokens is deprecated and incompatible with reasoning/o-series models.
            params["max_completion_tokens"] = config.max_tokens
        if config.stop_sequences:
            params["stop"] = config.stop_sequences

        params.update(provider_specific)
        return params

    def _build_responses_params(self, messages: List[Message], config: GenerationConfig) -> Dict[str, Any]:
        provider_specific = dict(config.provider_specific or {})
        effort = provider_specific.pop("reasoning_effort", None)
        if "reasoning" not in provider_specific and effort is not None:
            provider_specific["reasoning"] = {"effort": effort}
        response_format = provider_specific.pop("response_format", None)
        if isinstance(response_format, dict):
            text_cfg = provider_specific.get("text")
            if not isinstance(text_cfg, dict):
                text_cfg = {}
            else:
                text_cfg = dict(text_cfg)
            text_cfg.setdefault("format", response_format)
            provider_specific["text"] = text_cfg

        params: Dict[str, Any] = {
            "model": self._model,
            "input": self._convert_messages(messages),
        }

        sampling_allowed = self._sampling_allowed_for_model(provider_specific)
        if sampling_allowed:
            if config.temperature is not None:
                params["temperature"] = config.temperature
            if config.top_p is not None:
                params["top_p"] = config.top_p
        else:
            provider_specific.pop("temperature", None)
            provider_specific.pop("top_p", None)
            provider_specific.pop("logprobs", None)

        if config.max_tokens is not None:
            params["max_output_tokens"] = config.max_tokens

        params.update(provider_specific)
        return params

    def _should_fallback_to_responses(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        triggers = (
            "not compatible",
            "max_tokens",
            "max completion tokens",
            "unsupported parameter",
            "chat.completions",
            "responses api",
            "does not support",
            "temperature",
            "top_p",
            "reasoning effort",
            "reasoning model",
        )
        return self._is_reasoning_model() and any(t in msg for t in triggers)

    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert our Message format to OpenAI's format."""
        openai_messages = []

        for msg in messages:
            openai_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }

            # Handle file attachments - append their text content to the message
            if msg.attachments:
                file_contents = []
                for attachment in msg.attachments:
                    if "content" in attachment:
                        # File content provided directly
                        filename = attachment.get("filename", "file")
                        file_contents.append(f"\n\n--- {filename} ---\n{attachment['content']}")
                    elif "path" in attachment:
                        # File path provided - read it
                        try:
                            with open(attachment["path"], "r") as f:
                                content = f.read()
                                filename = attachment.get("filename", attachment["path"])
                                file_contents.append(f"\n\n--- {filename} ---\n{content}")
                        except Exception as e:
                            file_contents.append(f"\n\n[Error reading {attachment['path']}: {e}]")

                # Append all file contents to the message content
                if file_contents:
                    openai_msg["content"] = msg.content + "".join(file_contents)

            openai_messages.append(openai_msg)

        return openai_messages

    def _convert_chat_response(self, openai_response) -> ModelResponse:
        """Convert OpenAI Chat Completions response to ModelResponse."""
        choice = openai_response.choices[0]
        content = choice.message.content or ""

        # Extract token usage
        usage = openai_response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens

        # Estimate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="openai",
        )
        cost = self.estimate_cost(temp_response)

        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=openai_response.model,
            provider="openai",
            finish_reason=choice.finish_reason,
            estimated_cost_usd=cost,
            raw_response=openai_response.model_dump(),
        )

    def _convert_responses_response(self, response) -> ModelResponse:
        """Convert OpenAI Responses API response to ModelResponse."""
        content = getattr(response, "output_text", "") or ""
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0)

        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=getattr(response, "model", self._model),
            provider="openai",
        )
        cost = self.estimate_cost(temp_response)

        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=getattr(response, "model", self._model),
            provider="openai",
            finish_reason=str(getattr(response, "status", "")) or None,
            estimated_cost_usd=cost,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
        )
