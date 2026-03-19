# Groq implementation of the LLM Gateway interface (OpenAI-compatible API).

from typing import Optional, List
from openai import AsyncOpenAI
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)


class GroqGateway(LLMGateway):
    """
    Uses Groq's OpenAI-compatible endpoint. Requires GROQ_API_KEY.
    """

    PRICING = {
        # Prices per 1M tokens (subject to change; informational only)
        "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
        "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    }

    def __init__(self, api_key: str, model: str = "llama-3.1-8b-instant"):
        self._model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    async def generate(self, messages: List[Message], config: Optional[GenerationConfig] = None) -> ModelResponse:
        config = config or GenerationConfig()
        config = self.validate_config(config)

        groq_messages = [{"role": msg.role.value, "content": msg.content} for msg in messages]
        api_params = {"model": self._model, "messages": groq_messages}
        if config.temperature is not None:
            api_params["temperature"] = config.temperature
        if config.top_p is not None:
            api_params["top_p"] = config.top_p
        if config.max_tokens is not None:
            api_params["max_tokens"] = config.max_tokens
        if config.stop_sequences:
            api_params["stop"] = config.stop_sequences
        api_params.update(config.provider_specific)

        response = await self.client.chat.completions.create(**api_params)
        choice = response.choices[0]
        usage = response.usage
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens

        tmp = ModelResponse(
            content=choice.message.content or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=usage.total_tokens,
            model_name=self._model,
            provider="groq",
        )
        cost = self.estimate_cost(tmp)

        return ModelResponse(
            content=choice.message.content or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=usage.total_tokens,
            model_name=response.model,
            provider="groq",
            finish_reason=choice.finish_reason,
            estimated_cost_usd=cost,
            raw_response=response.model_dump(),
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "groq"

    @property
    def supports_files(self) -> bool:
        return False

    def estimate_cost(self, response: ModelResponse) -> float:
        key = None
        for k in self.PRICING.keys():
            if k in response.model_name:
                key = k
                break
        if not key:
            return 0.0
        pricing = self.PRICING[key]
        return (response.input_tokens / 1_000_000) * pricing["input"] + (response.output_tokens / 1_000_000) * pricing["output"]
