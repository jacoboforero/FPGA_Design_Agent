"""
LLM-driven helper utilities for the spec checklist workflow.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from agents.common.llm_gateway import GenerationConfig, Message, MessageRole
from core.observability.agentops_tracker import get_tracker
from agents.spec_helper.checklist import (
    CHECKLIST_SCHEMA,
    FieldInfo,
    build_empty_checklist,
    json_like_copy,
    merge_checklists,
)


def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


def _log_llm_call(stage: str, spec: Dict[str, Any], resp: Any) -> None:
    tracker = get_tracker()
    try:
        tracker.log_llm_call(
            agent="spec_helper",
            node_id=spec.get("module_name"),
            model=getattr(resp, "model_name", "unknown"),
            provider=getattr(resp, "provider", "unknown"),
            prompt_tokens=getattr(resp, "input_tokens", 0),
            completion_tokens=getattr(resp, "output_tokens", 0),
            total_tokens=getattr(resp, "total_tokens", 0),
            estimated_cost_usd=getattr(resp, "estimated_cost_usd", None),
            metadata={"stage": stage},
        )
    except Exception:
        pass


def _schema_json() -> str:
    return json.dumps(CHECKLIST_SCHEMA, indent=2)


def _truncate_text(text: str, limit: int = 4000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def _field_shape_hint(field: FieldInfo, *, user_facing: bool) -> str:
    if field.field_type == "text":
        return "Provide a short sentence or paragraph." if user_facing else "Value must be a JSON string."
    if field.field_type == "list":
        return "Provide a short bullet list." if user_facing else "Value must be a JSON array of strings."
    if field.field_type == "map":
        return (
            "Provide a small key/value map (e.g., name: description)."
            if user_facing
            else "Value must be a JSON object with string keys."
        )
    if field.field_type == "object":
        if field.item_keys:
            keys = ", ".join(field.item_keys)
            return (
                f"Provide values for these keys: {keys}."
                if user_facing
                else f"Value must be a JSON object with keys: {keys}."
            )
        return "Provide the object details." if user_facing else "Value must be a JSON object."
    if field.field_type == "list_of_objects":
        if field.item_keys:
            keys = ", ".join(field.item_keys)
            return (
                f"Provide a list of items with keys: {keys}."
                if user_facing
                else f"Value must be a JSON array of objects with keys: {keys}."
            )
        return "Provide a list of items." if user_facing else "Value must be a JSON array of objects."
    return "Provide the missing details." if user_facing else "Value must match the field type."


def _default_cfg(max_tokens: int, temperature: float) -> GenerationConfig:
    return GenerationConfig(temperature=temperature, max_tokens=max_tokens)


def _resolve_cfg(stage: str) -> GenerationConfig:
    if stage == "question":
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SPEC_QUESTION", "200"))
        temperature = float(os.getenv("LLM_TEMPERATURE_SPEC_QUESTION", "0.3"))
    elif stage == "draft":
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SPEC_DRAFT", "500"))
        temperature = float(os.getenv("LLM_TEMPERATURE_SPEC_DRAFT", "0.4"))
    else:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SPEC", "4000"))
        temperature = float(os.getenv("LLM_TEMPERATURE_SPEC", "0.2"))
    return _default_cfg(max_tokens, temperature)


def _run_llm(gateway: object, messages: List[Message], stage: str) -> str:
    if not gateway or not Message or not MessageRole:
        raise RuntimeError("LLM gateway is not available; set USE_LLM=1 and provider keys.")
    cfg = _resolve_cfg(stage)
    provider = getattr(gateway, "provider", None)
    json_mode = os.getenv("LLM_JSON_MODE", "1") != "0"
    if json_mode and provider in ("openai", "groq"):
        cfg.provider_specific.setdefault("response_format", {"type": "json_object"})

    async def _generate() -> Any:
        return await gateway.generate(messages=messages, config=cfg)  # type: ignore[arg-type]

    resp = asyncio.run(_generate())
    _log_llm_call(stage, {}, resp)
    return resp.content.strip()


def update_checklist_from_spec(
    gateway: object,
    spec_text: str,
    current_checklist: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    checklist = json_like_copy(current_checklist or build_empty_checklist())
    system = (
        "You are Spec Helper, an assistant for hardware engineers and students. "
        "Populate the L1-L5 checklist from the user's spec. "
        "Only fill fields that are explicitly stated or clearly implied. "
        "Do not invent missing details; leave them empty unless the spec says 'none' or 'n/a'. "
        "The spec may already follow the L1-L5 template with headings like "
        "'Role summary', 'Key rules', 'Performance intent', 'Reset semantics', "
        "'Transaction unit', 'Reset constraints', 'Resource strategy', "
        "'Latency budget', 'Assertion plan', and 'Acceptance metrics'. "
        "Map those headings directly to the corresponding fields. "
        "Other common headings map as follows: "
        "'L1 Functional intent' -> role_summary + key_rules, "
        "'Reset rules' -> reset_semantics, "
        "'Edge cases' -> corner_cases, "
        "'L2 Interface' -> signals, "
        "'Handshake semantics' -> handshake_semantics, "
        "'Params/defaults' -> configuration_parameters, "
        "'L3 Verification' -> test_goals, "
        "'Oracle plan' -> oracle_strategy, "
        "'Stimulus strategy' -> stimulus_strategy, "
        "'Pass/fail criteria' -> pass_fail_criteria, "
        "'Coverage goals' -> coverage_targets, "
        "'L4 Architecture' -> block_diagram/resource_strategy/latency_budget, "
        "'L5 Acceptance' -> required_artifacts/acceptance_metrics/exclusions. "
        "Treat headings ending with ':' as field labels. "
        "For list sections, collect subsequent bullet lines ('- ') until the next heading. "
        "For single-line fields like 'Role summary: ...' copy the value text directly. "
        "Do not leave required fields empty if the spec text provides values. "
        "If a field is explicitly not applicable, use a sentinel so it's treated as complete: "
        "text -> 'none', list -> ['none'], map -> {'note': 'none'}, object -> {'note': 'none'}, list_of_objects -> "
        "[{'name': 'none', 'direction': 'none', 'width': 'none'}] or equivalent for that field. "
        "Use proper JSON types for values: numbers as numbers (e.g., min_cycles_after_reset is an integer). "
        "Return JSON only, no prose, no code fences."
    )
    user = (
        "Checklist schema (types + descriptions):\n"
        f"{_schema_json()}\n\n"
        "Spec text:\n"
        f"{spec_text}\n\n"
        "Return JSON with a single key 'checklist'. "
        "Include only fields you can confidently populate; omit missing fields. "
        "For list fields, return arrays; for list_of_objects, return arrays of objects with the required keys."
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content=system),
        Message(role=MessageRole.USER, content=user),
    ]
    content = _run_llm(gateway, messages, stage="extract")
    parsed = _safe_json(content)
    if not parsed:
        retry_system = (
            "Return only a single valid JSON object. "
            "No explanations, no markdown, no extra text."
        )
        retry_messages = [
            Message(role=MessageRole.SYSTEM, content=retry_system),
            Message(role=MessageRole.USER, content=user),
        ]
        content = _run_llm(gateway, retry_messages, stage="extract")
        parsed = _safe_json(content)
    if not parsed:
        return checklist
    updated = parsed.get("checklist") if isinstance(parsed, dict) else None
    if not isinstance(updated, dict):
        return checklist
    return merge_checklists(checklist, updated)


def generate_followup_question(
    gateway: object,
    field: FieldInfo,
    checklist: Dict[str, Any],
    spec_text: str,
) -> str:
    system = (
        "You are Spec Helper, a concise hardware spec assistant. "
        "Ask one clear question to fill the missing field. "
        "If the field expects structured data, ask for the required keys by name. "
        "If the spec already mentions the answer, ask the user to paste or restate the exact content. "
        "Avoid mentioning JSON or data types. "
        "Do not mention L1-L5. Address a hardware engineer or student without assuming expertise."
    )
    field_context = {
        "path": field.path,
        "description": field.description,
    }
    user = (
        "Missing field info:\n"
        f"{json.dumps(field_context, indent=2)}\n\n"
        f"Field shape hint: {_field_shape_hint(field, user_facing=True)}\n\n"
        "Spec text (source of truth):\n"
        f"{_truncate_text(spec_text)}\n\n"
        "Return JSON with key 'question'."
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content=system),
        Message(role=MessageRole.USER, content=user),
    ]
    content = _run_llm(gateway, messages, stage="question")
    parsed = _safe_json(content)
    if parsed and isinstance(parsed.get("question"), str):
        return parsed["question"].strip()
    return field.description or f"Provide {field.path.replace('.', ' ')}."


def generate_field_draft(
    gateway: object,
    field: FieldInfo,
    checklist: Dict[str, Any],
    spec_text: str,
) -> Dict[str, Any]:
    system = (
        "You are Spec Helper, drafting missing checklist details for a hardware spec. "
        "Generate a proposal based on the spec context. "
        "Return JSON only with keys: draft_text (human-readable) and value (matches the field type). "
        "Use proper JSON types for values; numeric fields must be numbers, not prose. "
        "If the correct answer is 'none' or not applicable, set value to the sentinel: "
        "text -> 'none', list -> ['none'], map -> {'note': 'none'}, object -> {'note': 'none'}, list_of_objects -> "
        "[{'name': 'none', 'direction': 'none', 'width': 'none'}] or equivalent for that field."
    )
    field_context = {
        "path": field.path,
        "description": field.description,
        "type": field.field_type,
        "item_keys": field.item_keys or [],
    }
    user = (
        "Field info:\n"
        f"{json.dumps(field_context, indent=2)}\n\n"
        f"Field shape hint: {_field_shape_hint(field, user_facing=False)}\n\n"
        "Spec text:\n"
        f"{_truncate_text(spec_text)}\n\n"
        "Return JSON with draft_text and value."
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content=system),
        Message(role=MessageRole.USER, content=user),
    ]
    content = _run_llm(gateway, messages, stage="draft")
    parsed = _safe_json(content) or {}
    return {
        "draft_text": parsed.get("draft_text", "").strip() if isinstance(parsed, dict) else "",
        "value": parsed.get("value") if isinstance(parsed, dict) else None,
    }
