"""
LLM-driven helper utilities for the spec checklist workflow.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, apply_reproducibility_settings
from core.observability.agentops_tracker import get_tracker
from core.prompting import (
    apply_prompt_output_contract,
    build_prompt_metadata,
    parse_json_object,
    RenderedPrompt,
    render_prompt,
    write_prompt_trace,
)
from core.runtime.config import get_runtime_config
from agents.spec_helper.checklist import (
    CHECKLIST_SCHEMA,
    FieldInfo,
    build_empty_checklist,
    json_like_copy,
    merge_checklists,
)


def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    return parse_json_object(text)


def _log_llm_call(stage: str, spec: Dict[str, Any], resp: Any, prompt_meta: dict[str, Any]) -> None:
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
            metadata={**prompt_meta, "stage": stage},
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


def _user_facing_field_path(path: str) -> str:
    mapping = {
        "L1.": "functional intent.",
        "L2.": "interface details.",
        "L3.": "verification plan.",
        "L4.": "architecture plan.",
        "L5.": "acceptance criteria.",
    }
    for prefix, replacement in mapping.items():
        if path.startswith(prefix):
            return path.replace(prefix, replacement, 1)
    return path


def _default_cfg(max_tokens: int, temperature: float) -> GenerationConfig:
    top_p = get_runtime_config().llm.top_p
    cfg = GenerationConfig(temperature=temperature, top_p=top_p, max_tokens=max_tokens)
    return apply_reproducibility_settings(cfg, provider=get_runtime_config().llm.provider)


def _resolve_cfg(stage: str) -> GenerationConfig:
    llm_cfg = get_runtime_config().llm
    if stage == "question":
        max_tokens = int(llm_cfg.max_tokens_spec_question)
        temperature = float(llm_cfg.temperature_spec_question)
    elif stage == "draft":
        max_tokens = int(llm_cfg.max_tokens_spec_draft)
        temperature = float(llm_cfg.temperature_spec_draft)
    else:
        max_tokens = int(llm_cfg.max_tokens_spec)
        temperature = float(llm_cfg.temperature_spec)
    return _default_cfg(max_tokens, temperature)


def _run_llm(
    gateway: object,
    prompt: RenderedPrompt,
    stage: str,
    *,
    trace_dir: Optional[Path] = None,
    spec: Optional[Dict[str, Any]] = None,
) -> str:
    if not gateway or not Message or not MessageRole:
        raise RuntimeError("LLM gateway is not available; set USE_LLM=1 and provider keys.")
    cfg = apply_prompt_output_contract(_resolve_cfg(stage), prompt)
    write_prompt_trace(prompt, trace_dir)

    async def _generate() -> Any:
        return await gateway.generate(messages=prompt.messages, config=cfg)  # type: ignore[arg-type]

    resp = asyncio.run(_generate())
    _log_llm_call(stage, spec or {}, resp, build_prompt_metadata(prompt))
    return resp.content.strip()


def update_checklist_from_spec(
    gateway: object,
    spec_text: str,
    current_checklist: Optional[Dict[str, Any]] = None,
    *,
    trace_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    checklist = json_like_copy(current_checklist or build_empty_checklist())
    prompt = render_prompt(
        "spec_helper.extract",
        {
            "checklist_schema_json": _schema_json(),
            "spec_text": spec_text,
        },
    )
    content = _run_llm(gateway, prompt, stage="extract", trace_dir=trace_dir, spec=checklist)
    parsed = _safe_json(content)
    if not parsed:
        retry_prompt = render_prompt(
            "spec_helper.extract_retry",
            {
                "checklist_schema_json": _schema_json(),
                "spec_text": spec_text,
            },
        )
        content = _run_llm(gateway, retry_prompt, stage="extract", trace_dir=trace_dir, spec=checklist)
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
    *,
    area_label: str | None = None,
    display_label: str | None = None,
    planning_goal: str | None = None,
    trace_dir: Optional[Path] = None,
) -> str:
    field_context = {
        "detail": display_label or _user_facing_field_path(field.path),
        "description": field.description,
    }
    if area_label:
        field_context["area"] = area_label
    if planning_goal:
        field_context["goal"] = planning_goal
    prompt = render_prompt(
        "spec_helper.followup",
        {
            "field_context_json": json.dumps(field_context, indent=2),
            "field_shape_hint": _field_shape_hint(field, user_facing=True),
            "spec_text": _truncate_text(spec_text),
        },
    )
    content = _run_llm(
        gateway,
        prompt,
        stage="question",
        trace_dir=trace_dir,
        spec={"module_name": checklist.get("module_name")},
    )
    parsed = _safe_json(content)
    if parsed and isinstance(parsed.get("question"), str):
        return parsed["question"].strip()
    fallback_label = display_label or _user_facing_field_path(field.path)
    return field.description or f"Please clarify {fallback_label}."


def generate_field_draft(
    gateway: object,
    field: FieldInfo,
    checklist: Dict[str, Any],
    spec_text: str,
    *,
    trace_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    field_context = {
        "path": field.path,
        "description": field.description,
        "type": field.field_type,
        "item_keys": field.item_keys or [],
    }
    parent_key = field.path.split(".", 1)[0] if "." in field.path else None
    relevant_checklist: Dict[str, Any] = {"module_name": checklist.get("module_name")}
    if parent_key and isinstance(checklist.get(parent_key), dict):
        relevant_checklist[parent_key] = checklist.get(parent_key)
    prompt = render_prompt(
        "spec_helper.draft",
        {
            "field_context_json": json.dumps(field_context, indent=2),
            "field_shape_hint": _field_shape_hint(field, user_facing=False),
            "relevant_checklist_json": json.dumps(relevant_checklist, indent=2),
            "spec_text": _truncate_text(spec_text),
        },
    )
    content = _run_llm(gateway, prompt, stage="draft", trace_dir=trace_dir, spec=checklist)
    parsed = _safe_json(content) or {}
    return {
        "draft_text": parsed.get("draft_text", "").strip() if isinstance(parsed, dict) else "",
        "value": parsed.get("value") if isinstance(parsed, dict) else None,
    }


def generate_field_draft_options(
    gateway: object,
    field: FieldInfo,
    checklist: Dict[str, Any],
    spec_text: str,
    *,
    n_options: int = 3,
    trace_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Generate multiple candidate drafts for a single missing field.

    Returns a list of objects with keys: draft_text (human-readable) and value (typed for the field).
    """
    n_options = max(1, min(int(n_options), 5))
    field_context = {
        "path": field.path,
        "description": field.description,
        "type": field.field_type,
        "item_keys": field.item_keys or [],
    }
    parent_key = field.path.split(".", 1)[0] if "." in field.path else None
    relevant_checklist: Dict[str, Any] = {"module_name": checklist.get("module_name")}
    if parent_key and isinstance(checklist.get(parent_key), dict):
        relevant_checklist[parent_key] = checklist.get(parent_key)
    prompt = render_prompt(
        "spec_helper.draft_options",
        {
            "n_options": n_options,
            "field_context_json": json.dumps(field_context, indent=2),
            "field_shape_hint": _field_shape_hint(field, user_facing=False),
            "relevant_checklist_json": json.dumps(relevant_checklist, indent=2),
            "spec_text": _truncate_text(spec_text),
        },
    )
    content = _run_llm(gateway, prompt, stage="draft", trace_dir=trace_dir, spec=checklist)
    parsed = _safe_json(content) or {}
    options = parsed.get("options") if isinstance(parsed, dict) else None
    if isinstance(options, list):
        normalized: List[Dict[str, Any]] = []
        for opt in options:
            if not isinstance(opt, dict):
                continue
            normalized.append(
                {
                    "draft_text": str(opt.get("draft_text") or "").strip(),
                    "value": opt.get("value"),
                }
            )
        if normalized:
            return normalized[:n_options]

    # Fallback: single draft
    one = generate_field_draft(gateway, field, checklist, spec_text, trace_dir=trace_dir)
    return [one]
