from __future__ import annotations

import asyncio
from types import SimpleNamespace

from adapters.llm.adapter_openai import OpenAIGateway
from adapters.llm.gateway import GenerationConfig, Message, MessageRole


def _messages() -> list[Message]:
    return [
        Message(role=MessageRole.SYSTEM, content="You are concise."),
        Message(role=MessageRole.USER, content="Generate RTL."),
    ]


def _fake_chat_response(content: str = "chat ok", model: str = "gpt-4.1-mini"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        ),
        model=model,
        model_dump=lambda: {"kind": "chat"},
    )


def _fake_responses_response(content: str = "responses ok", model: str = "gpt-5-mini"):
    return SimpleNamespace(
        output_text=content,
        usage=SimpleNamespace(
            input_tokens=13,
            output_tokens=5,
            total_tokens=18,
        ),
        model=model,
        status="completed",
        model_dump=lambda: {"kind": "responses"},
    )


def test_gpt41_auto_mode_uses_chat_api(monkeypatch):
    monkeypatch.delenv("OPENAI_API_MODE", raising=False)
    gateway = OpenAIGateway(api_key="test-key", model="gpt-4.1-mini")

    captured: dict = {}

    async def fake_chat_create(**kwargs):
        captured.update(kwargs)
        return _fake_chat_response(model="gpt-4.1-mini-2025-04-14")

    async def fail_responses_create(**kwargs):
        raise AssertionError("responses API should not be used for gpt-4.1 auto mode")

    monkeypatch.setattr(gateway.client.chat.completions, "create", fake_chat_create)
    monkeypatch.setattr(gateway.client.responses, "create", fail_responses_create)

    response = asyncio.run(
        gateway.generate(
            _messages(),
            GenerationConfig(
                max_tokens=128,
                temperature=0.3,
                top_p=0.8,
                stop_sequences=["END"],
            ),
        )
    )

    assert captured["model"] == "gpt-4.1-mini"
    assert captured["max_completion_tokens"] == 128
    assert "max_tokens" not in captured
    assert captured["temperature"] == 0.3
    assert captured["top_p"] == 0.8
    assert captured["stop"] == ["END"]
    assert response.content == "chat ok"
    assert response.model_name == "gpt-4.1-mini-2025-04-14"


def test_gpt5_auto_mode_uses_responses_api_and_drops_sampling(monkeypatch):
    monkeypatch.delenv("OPENAI_API_MODE", raising=False)
    gateway = OpenAIGateway(api_key="test-key", model="gpt-5-mini")

    captured: dict = {}

    async def fail_chat_create(**kwargs):
        raise AssertionError("chat API should not be used for gpt-5 auto mode")

    async def fake_responses_create(**kwargs):
        captured.update(kwargs)
        return _fake_responses_response(model="gpt-5-mini-2025-08-07")

    monkeypatch.setattr(gateway.client.chat.completions, "create", fail_chat_create)
    monkeypatch.setattr(gateway.client.responses, "create", fake_responses_create)

    response = asyncio.run(
        gateway.generate(
            _messages(),
            GenerationConfig(
                max_tokens=96,
                temperature=0.6,
                top_p=0.9,
                stop_sequences=["END"],
            ),
        )
    )

    assert captured["model"] == "gpt-5-mini"
    assert captured["max_output_tokens"] == 96
    assert "temperature" not in captured
    assert "top_p" not in captured
    assert "stop" not in captured
    text_cfg = captured.get("text")
    if isinstance(text_cfg, dict):
        assert "stop" not in text_cfg
    assert response.content == "responses ok"
    assert response.model_name == "gpt-5-mini-2025-08-07"


def test_chat_mode_falls_back_to_responses_for_compatibility_errors(monkeypatch):
    monkeypatch.setenv("OPENAI_API_MODE", "chat")
    gateway = OpenAIGateway(api_key="test-key", model="gpt-5-mini")

    calls = {"chat": 0, "responses": 0}

    async def fake_chat_create(**kwargs):
        calls["chat"] += 1
        raise RuntimeError("Unsupported parameter: max_tokens. Use Responses API for this model.")

    async def fake_responses_create(**kwargs):
        calls["responses"] += 1
        return _fake_responses_response(model="gpt-5-mini-2025-08-07")

    monkeypatch.setattr(gateway.client.chat.completions, "create", fake_chat_create)
    monkeypatch.setattr(gateway.client.responses, "create", fake_responses_create)

    response = asyncio.run(gateway.generate(_messages(), GenerationConfig(max_tokens=64)))

    assert calls["chat"] == 1
    assert calls["responses"] == 1
    assert response.content == "responses ok"


def test_responses_maps_reasoning_effort_and_allows_sampling_for_gpt52_none(monkeypatch):
    monkeypatch.delenv("OPENAI_API_MODE", raising=False)
    gateway = OpenAIGateway(api_key="test-key", model="gpt-5.2-mini")

    captured: dict = {}

    async def fake_responses_create(**kwargs):
        captured.update(kwargs)
        return _fake_responses_response(model="gpt-5.2-mini-2025-10-01")

    monkeypatch.setattr(gateway.client.responses, "create", fake_responses_create)

    response = asyncio.run(
        gateway.generate(
            _messages(),
            GenerationConfig(
                max_tokens=80,
                temperature=0.2,
                top_p=0.7,
                provider_specific={"reasoning_effort": "none"},
            ),
        )
    )

    assert captured["reasoning"] == {"effort": "none"}
    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.7
    assert response.model_name == "gpt-5.2-mini-2025-10-01"


def test_chat_maps_reasoning_object_to_reasoning_effort(monkeypatch):
    monkeypatch.setenv("OPENAI_API_MODE", "chat")
    gateway = OpenAIGateway(api_key="test-key", model="gpt-4.1-mini")

    captured: dict = {}

    async def fake_chat_create(**kwargs):
        captured.update(kwargs)
        return _fake_chat_response(model="gpt-4.1-mini-2025-04-14")

    monkeypatch.setattr(gateway.client.chat.completions, "create", fake_chat_create)

    asyncio.run(
        gateway.generate(
            _messages(),
            GenerationConfig(provider_specific={"reasoning": {"effort": "medium"}}),
        )
    )

    assert captured["reasoning_effort"] == "medium"
    assert "reasoning" not in captured


def test_responses_maps_response_format_into_text_format(monkeypatch):
    monkeypatch.setenv("OPENAI_API_MODE", "responses")
    gateway = OpenAIGateway(api_key="test-key", model="gpt-5-mini")

    captured: dict = {}

    async def fake_responses_create(**kwargs):
        captured.update(kwargs)
        return _fake_responses_response(model="gpt-5-mini-2025-08-07")

    monkeypatch.setattr(gateway.client.responses, "create", fake_responses_create)

    response = asyncio.run(
        gateway.generate(
            _messages(),
            GenerationConfig(provider_specific={"response_format": {"type": "json_object"}}),
        )
    )

    assert "response_format" not in captured
    assert isinstance(captured.get("text"), dict)
    assert captured["text"]["format"] == {"type": "json_object"}
    assert response.content == "responses ok"
