"""
L1-L5 checklist schema and helpers for the spec helper workflow.
Matches core/schemas/specifications.py fields.
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
        "role_summary": {
            "type": "text",
            "description": "One paragraph summary of the hardware block's responsibility.",
        },
        "key_rules": {
            "type": "list",
            "description": "Ordering, losslessness, flag, or error rules.",
        },
        "performance_intent": {
            "type": "text",
            "description": "Qualitative throughput/latency expectations.",
        },
        "reset_semantics": {
            "type": "text",
            "description": "Definition of what safe after reset means.",
        },
        "corner_cases": {
            "type": "list",
            "description": "Corner or illegal scenarios that must be handled.",
        },
        "open_questions": {
            "type": "list",
            "description": "Outstanding questions before freezing.",
            "optional": True,
        },
    },
    "L2": {
        "clocking": {
            "type": "list_of_objects",
            "item_keys": ["clock_name"],
            "description": "Clock/reset domains and polarity details.",
        },
        "signals": {
            "type": "list_of_objects",
            "item_keys": ["name", "direction", "width_expr"],
            "description": "I/O table entries (direction INPUT/OUTPUT/INOUT, width expression).",
        },
        "handshake_semantics": {
            "type": "list_of_objects",
            "item_keys": ["name", "rules"],
            "description": "Protocol/backpressure semantics.",
            "optional": True,
        },
        "transaction_unit": {
            "type": "text",
            "description": "Beat/packet/word and ordering guarantees.",
        },
        "configuration_parameters": {
            "type": "list_of_objects",
            "item_keys": ["name"],
            "description": "Config params with defaults and notes.",
            "optional": True,
        },
    },
    "L3": {
        "test_goals": {
            "type": "list",
            "description": "Happy-path, boundary, and illegal goals.",
        },
        "oracle_strategy": {
            "type": "text",
            "description": "Scoreboard or reference model plan.",
        },
        "stimulus_strategy": {
            "type": "text",
            "description": "Directed scenarios plus randomization ranges.",
        },
        "pass_fail_criteria": {
            "type": "list",
            "description": "Global pass/fail rules.",
        },
        "coverage_targets": {
            "type": "list_of_objects",
            "item_keys": ["coverage_id", "description", "metric_type"],
            "description": "Coverage targets and thresholds.",
            "optional": True,
        },
        "reset_constraints": {
            "type": "object",
            "item_keys": ["min_cycles_after_reset"],
            "description": "Reset sequencing constraints.",
        },
        "scenarios": {
            "type": "list_of_objects",
            "item_keys": ["scenario_id", "description", "stimulus", "oracle", "pass_fail_criteria"],
            "description": "Detailed verification scenarios.",
            "optional": True,
        },
    },
    "L4": {
        "block_diagram": {
            "type": "list_of_objects",
            "item_keys": ["node_id", "description", "node_type"],
            "description": "Block diagram nodes for the design.",
        },
        "dependencies": {
            "type": "list_of_objects",
            "item_keys": ["parent_id", "child_id", "dependency_type"],
            "description": "Dependency edges between blocks.",
            "optional": True,
        },
        "clock_domains": {
            "type": "list_of_objects",
            "item_keys": ["name"],
            "description": "Clock domains and rates.",
            "optional": True,
        },
        "resource_strategy": {
            "type": "text",
            "description": "Resource allocations (FIFO/RAM sizes, etc.).",
        },
        "latency_budget": {
            "type": "text",
            "description": "Latency/throughput plan tied back to L3.",
        },
        "assertion_plan": {
            "type": "object",
            "item_keys": ["sva", "scoreboard_assertions"],
            "description": "Assertions and scoreboard checks.",
        },
    },
    "L5": {
        "required_artifacts": {
            "type": "list_of_objects",
            "item_keys": ["name", "description"],
            "description": "Artifacts required for sign-off.",
        },
        "acceptance_metrics": {
            "type": "list_of_objects",
            "item_keys": ["metric_id", "description", "operator", "target_value"],
            "description": "Acceptance criteria for sign-off.",
        },
        "exclusions": {
            "type": "list",
            "description": "Explicit limitations or exclusions.",
            "optional": True,
        },
        "synthesis_target": {
            "type": "text",
            "description": "Target technology/tool (FPGA, ASIC, etc.).",
            "optional": True,
        },
    },
}


@dataclass(frozen=True)
class FieldInfo:
    path: str
    field_type: str
    description: str
    item_keys: List[str] | None = None
    optional: bool = False


def _empty_value(field_type: str) -> Any:
    if field_type in ("list", "list_of_objects"):
        return []
    if field_type in ("map", "object"):
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
                optional=field.get("optional", False),
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
    if field_type in ("map", "object"):
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


def _is_none_token(value: str) -> bool:
    return value.strip().lower() in ("none", "n/a", "na", "not applicable")


def _list_has_only_none(values: List[Any]) -> bool:
    if not values:
        return True
    for item in values:
        text = str(item).strip()
        if text and not _is_none_token(text):
            return False
    return True


def is_missing(value: Any, field: Dict[str, Any]) -> bool:
    field_type = field["type"]
    if field_type == "text":
        text = str(value or "").strip()
        return not text or _is_none_token(text)
    if field_type == "list":
        if not isinstance(value, list) or len(value) == 0:
            return True
        return _list_has_only_none(value)
    if field_type == "map":
        if not isinstance(value, dict) or len(value) == 0:
            return True
        return all(isinstance(v, str) and _is_none_token(v) for v in value.values())
    if field_type == "object":
        if not isinstance(value, dict) or len(value) == 0:
            return True
        required = field.get("item_keys") or []
        for key in required:
            val = value.get(key)
            if val is None:
                return True
            if isinstance(val, str) and not val.strip():
                return True
            if isinstance(val, str) and _is_none_token(val):
                return True
            if isinstance(val, list):
                if _list_has_only_none(val):
                    return True
                continue
        return False
    if field_type == "list_of_objects":
        if not isinstance(value, list) or len(value) == 0:
            return True
        required = field.get("item_keys") or []
        for item in value:
            if not isinstance(item, dict):
                continue
            ok = True
            for key in required:
                val = item.get(key)
                if val is None:
                    ok = False
                    break
                if isinstance(val, list):
                    if _list_has_only_none(val):
                        ok = False
                        break
                    continue
                text = str(val).strip()
                if not text or _is_none_token(text):
                    ok = False
                    break
            if ok:
                return False
        return True
    return value is None


def list_missing_fields(checklist: Dict[str, Any]) -> List[FieldInfo]:
    missing: List[FieldInfo] = []
    for path, field in _iter_fields(CHECKLIST_SCHEMA):
        value = get_field(checklist, path)
        if is_missing(value, field) and not field.get("optional", False):
            missing.append(
                FieldInfo(
                    path=path,
                    field_type=field["type"],
                    description=field.get("description", ""),
                    item_keys=field.get("item_keys"),
                    optional=field.get("optional", False),
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
