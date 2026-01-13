"""
L1-L5 checklist schema and helpers for the spec helper workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


CHECKLIST_SCHEMA: Dict[str, Any] = {
    "module_name": {
        "type": "text",
        "description": "Short module name (snake_case).",
    },
    "L1": {
        "functional_intent": {
            "type": "text",
            "description": "Plain-language behavior and purpose.",
        },
        "reset_rules": {
            "type": "text",
            "description": "Reset behavior and safe state after reset.",
        },
        "edge_cases": {
            "type": "list",
            "description": "Key edge/illegal cases that must be handled.",
        },
    },
    "L2": {
        "clock": {
            "type": "text",
            "description": "Clock signal name or 'none' if combinational.",
        },
        "reset": {
            "type": "text",
            "description": "Reset signal name or 'none' if no reset.",
        },
        "signals": {
            "type": "list_of_objects",
            "item_keys": ["name", "direction", "width"],
            "description": "I/O table entries: name, direction (INPUT/OUTPUT/INOUT), width, notes (optional).",
        },
        "handshake_semantics": {
            "type": "text",
            "description": "Protocol/backpressure/ready-valid semantics.",
        },
        "params_defaults": {
            "type": "list_of_objects",
            "item_keys": ["name", "default", "description"],
            "description": "Config params with defaults and notes.",
        },
    },
    "L3": {
        "test_goals": {
            "type": "list",
            "description": "Test goals (happy/boundary/illegal).",
        },
        "oracle_plan": {
            "type": "text",
            "description": "Scoreboard/reference model plan.",
        },
        "stimulus_strategy": {
            "type": "text",
            "description": "Directed/random stimulus strategy.",
        },
        "pass_fail_criteria": {
            "type": "text",
            "description": "Global pass/fail criteria.",
        },
        "coverage_goals": {
            "type": "map",
            "description": "Coverage targets (e.g., {'branch': 0.8, 'toggle': 0.7} or named goals).",
        },
    },
    "L4": {
        "architecture": {
            "type": "text",
            "description": "Block/FSM sketch or microarchitecture summary.",
        },
        "clocking_cdc": {
            "type": "text",
            "description": "Clocking/CDC notes and assumptions.",
        },
        "resource_choices": {
            "type": "text",
            "description": "Resource choices (buffers, RAMs, FIFOs).",
        },
        "latency_throughput": {
            "type": "text",
            "description": "Latency/throughput goals.",
        },
    },
    "L5": {
        "acceptance": {
            "type": "text",
            "description": "Definition of done.",
        },
        "required_artifacts": {
            "type": "list",
            "description": "Required artifacts (RTL, TB, reports).",
        },
        "coverage_thresholds": {
            "type": "map",
            "description": "Coverage thresholds for sign-off.",
        },
        "exclusions_assumptions": {
            "type": "list",
            "description": "Explicit exclusions and assumptions.",
        },
    },
}


@dataclass(frozen=True)
class FieldInfo:
    path: str
    field_type: str
    description: str
    item_keys: List[str] | None = None


def _empty_value(field_type: str) -> Any:
    if field_type in ("list", "list_of_objects"):
        return []
    if field_type == "map":
        return {}
    return ""


def _iter_fields(schema: Dict[str, Any], prefix: str = "") -> Iterable[Tuple[str, Dict[str, Any]]]:
    for key, value in schema.items():
        if isinstance(value, dict) and "type" in value:
            yield f"{prefix}{key}", value
        elif isinstance(value, dict):
            yield from _iter_fields(value, prefix=f"{prefix}{key}.")


def build_empty_checklist() -> Dict[str, Any]:
    def _build(schema: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in schema.items():
            if isinstance(value, dict) and "type" in value:
                out[key] = _empty_value(value["type"])
            elif isinstance(value, dict):
                out[key] = _build(value)
        return out

    return _build(CHECKLIST_SCHEMA)


def list_field_info() -> List[FieldInfo]:
    fields: List[FieldInfo] = []
    for path, field in _iter_fields(CHECKLIST_SCHEMA):
        fields.append(
            FieldInfo(
                path=path,
                field_type=field["type"],
                description=field.get("description", ""),
                item_keys=field.get("item_keys"),
            )
        )
    return fields


def get_field(checklist: Dict[str, Any], path: str) -> Any:
    cur: Any = checklist
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_field(checklist: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Dict[str, Any] = checklist
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _normalize_value(field: Dict[str, Any], value: Any) -> Any:
    field_type = field["type"]
    if field_type == "text":
        return "" if value is None else str(value).strip()
    if field_type == "list":
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []
    if field_type == "map":
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if k}
        text = str(value).strip() if value is not None else ""
        return {"notes": text} if text else {}
    if field_type == "list_of_objects":
        if value is None:
            return []
        items = value if isinstance(value, list) else [value]
        normalized: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized
    return value


def merge_checklists(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = json_like_copy(current)
    for path, field in _iter_fields(CHECKLIST_SCHEMA):
        new_value = _normalize_value(field, get_field(update, path))
        if not is_missing(new_value, field):
            set_field(merged, path, new_value)
    return merged


def is_missing(value: Any, field: Dict[str, Any]) -> bool:
    field_type = field["type"]
    if field_type == "text":
        return not str(value or "").strip()
    if field_type == "list":
        return not isinstance(value, list) or len(value) == 0
    if field_type == "map":
        return not isinstance(value, dict) or len(value) == 0
    if field_type == "list_of_objects":
        if not isinstance(value, list) or len(value) == 0:
            return True
        required = field.get("item_keys") or []
        for item in value:
            if not isinstance(item, dict):
                continue
            if all(str(item.get(k, "")).strip() for k in required):
                return False
        return True
    return value is None


def list_missing_fields(checklist: Dict[str, Any]) -> List[FieldInfo]:
    missing: List[FieldInfo] = []
    for path, field in _iter_fields(CHECKLIST_SCHEMA):
        value = get_field(checklist, path)
        if is_missing(value, field):
            missing.append(
                FieldInfo(
                    path=path,
                    field_type=field["type"],
                    description=field.get("description", ""),
                    item_keys=field.get("item_keys"),
                )
            )
    return missing


def json_like_copy(data: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-ish copy for JSON-like data structures."""
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[key] = json_like_copy(value)
        elif isinstance(value, list):
            out[key] = list(value)
        else:
            out[key] = value
    return out
