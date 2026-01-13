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
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SPEC", "1200"))
        temperature = float(os.getenv("LLM_TEMPERATURE_SPEC", "0.2"))
    return _default_cfg(max_tokens, temperature)


def _run_llm(gateway: object, messages: List[Message], stage: str) -> str:
    if not gateway or not Message or not MessageRole:
        raise RuntimeError("LLM gateway is not available; set USE_LLM=1 and provider keys.")
    cfg = _resolve_cfg(stage)

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
        "If a field is explicitly not applicable, use a sentinel so it's treated as complete: "
        "text -> 'none', list -> ['none'], map -> {'note': 'none'}, list_of_objects -> "
        "[{'name': 'none', 'direction': 'none', 'width': 'none'}] or equivalent for that field. "
        "If sign-off coverage thresholds are not specified but coverage goals are, "
        "copy coverage goals into L5.coverage_thresholds. "
        "Return JSON only, no prose, no code fences."
    )
    user = (
        "Checklist schema (types + descriptions):\n"
        f"{_schema_json()}\n\n"
        "Current checklist (may be empty):\n"
        f"{json.dumps(checklist, indent=2)}\n\n"
        "Spec text:\n"
        f"{spec_text}\n\n"
        "Return JSON with a single key 'checklist' whose value matches the schema exactly. "
        "Use empty string, empty list, or empty object when data is missing."
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content=system),
        Message(role=MessageRole.USER, content=user),
    ]
    content = _run_llm(gateway, messages, stage="extract")
    parsed = _safe_json(content)
    if not parsed:
        return checklist
    updated = parsed.get("checklist") if isinstance(parsed, dict) else None
    if not isinstance(updated, dict):
        return checklist
    return merge_checklists(checklist, updated)


def generate_followup_question(gateway: object, field: FieldInfo, checklist: Dict[str, Any]) -> str:
    system = (
        "You are Spec Helper, a concise hardware spec assistant. "
        "Ask one clear question to fill the missing field. "
        "Do not mention L1-L5. Address a hardware engineer or student without assuming expertise."
    )
    field_context = {
        "path": field.path,
        "description": field.description,
        "type": field.field_type,
        "item_keys": field.item_keys or [],
    }
    user = (
        "Missing field info:\n"
        f"{json.dumps(field_context, indent=2)}\n\n"
        "Current checklist (for context):\n"
        f"{json.dumps(checklist, indent=2)}\n\n"
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
        "If the correct answer is 'none' or not applicable, set value to the sentinel: "
        "text -> 'none', list -> ['none'], map -> {'note': 'none'}, list_of_objects -> "
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
        "Spec text:\n"
        f"{spec_text}\n\n"
        "Current checklist:\n"
        f"{json.dumps(checklist, indent=2)}\n\n"
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
