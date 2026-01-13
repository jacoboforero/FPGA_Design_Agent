"""
Interactive Spec Helper CLI: open an editor for the initial spec, then use
LLM-driven follow-ups to complete the L1-L5 checklist and lock the specs.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agents.common.llm_gateway import init_llm_gateway
from agents.spec_helper.checklist import (
    FieldInfo,
    build_empty_checklist,
    list_missing_fields,
    set_field,
)
from agents.spec_helper.llm_helper import (
    generate_field_draft,
    generate_followup_question,
    update_checklist_from_spec,
)

SPEC_DIR = Path("artifacts/task_memory/specs")

WELCOME_BANNER = r"""
========================================
  Welcome to the Hardware Design CLI
========================================
"""


def _print_banner() -> None:
    print(WELCOME_BANNER)
    print("Multi-Agent Hardware Design CLI\n")


def _sanitize_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"mod_{cleaned}"
    return cleaned


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    val = input(f"{prompt}{suffix} ").strip().lower()
    if val in ("n", "no"):
        return False
    if val in ("y", "yes"):
        return True
    return default


def _select_editor() -> List[str]:
    editor = os.getenv("EDITOR", "").strip()
    if editor:
        return shlex.split(editor)
    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]
    raise RuntimeError("No editor found. Set $EDITOR to your preferred editor.")


def _open_editor_for_spec() -> str:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    spec_path = SPEC_DIR / "spec_input.txt"
    if not spec_path.exists():
        spec_path.write_text("")
    print("Press Enter to open your editor and paste the initial specification.")
    print("Save and close the editor when you're done.")
    print(f"File: {spec_path}")
    try:
        input()
    except KeyboardInterrupt:
        print("\nAborted.")
        return ""
    cmd = _select_editor() + [str(spec_path)]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nAborted.")
        return ""
    return spec_path.read_text().strip()


def _append_spec_notes(spec_text: str, label: str, content: str) -> str:
    trimmed = content.strip()
    if not trimmed:
        return spec_text
    return f"{spec_text}\n\n[{label}]\n{trimmed}".strip()


def _normalize_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for sig in signals or []:
        if not isinstance(sig, dict):
            continue
        entry = dict(sig)
        if "direction" in entry and isinstance(entry["direction"], str):
            entry["direction"] = entry["direction"].upper()
        normalized.append(entry)
    return normalized


def _clock_reset_dict(value: str) -> Dict[str, Any]:
    lowered = value.strip().lower()
    if lowered in ("none", "n/a", "na", "combinational", "no clock", "no reset", ""):
        return {}
    return {"name": value.strip()}


def _none_value(field: FieldInfo) -> Any:
    field_type = field.field_type
    if field_type == "text":
        return "none"
    if field_type == "list":
        return ["none"]
    if field_type == "map":
        return {"note": "none"}
    if field_type == "list_of_objects":
        keys = field.item_keys or []
        if keys:
            return [{key: "none" for key in keys}]
        return [{"note": "none"}]
    return "none"


def _is_none_token(value: str) -> bool:
    return value.strip().lower() in ("none", "n/a", "na")


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if _is_none_token(text) else text


def _clean_list(values: Any) -> List[Any]:
    if not isinstance(values, list):
        return []
    if not values:
        return []
    cleaned: List[Any] = []
    for item in values:
        if isinstance(item, str):
            if _is_none_token(item):
                continue
            cleaned.append(item)
        else:
            cleaned.append(item)
    return cleaned


def _dict_all_none(item: Dict[str, Any]) -> bool:
    if not item:
        return True
    for val in item.values():
        if isinstance(val, str):
            if not _is_none_token(val):
                return False
        elif val not in (None, "", []):
            return False
    return True


def _clean_list_of_objects(values: Any) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        if _dict_all_none(item):
            continue
        cleaned.append(item)
    return cleaned


def _clean_map(values: Any) -> Dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    if not values:
        return {}
    if all(isinstance(v, str) and _is_none_token(v) for v in values.values()):
        return {}
    return values


def _coerce_answer_value(field: FieldInfo, value: Any) -> Any:
    if value is None:
        return _none_value(field)
    if field.field_type == "text":
        return value if str(value).strip() else _none_value(field)
    if field.field_type == "list":
        return value if isinstance(value, list) and value else _none_value(field)
    if field.field_type == "map":
        return value if isinstance(value, dict) and value else _none_value(field)
    if field.field_type == "list_of_objects":
        return value if isinstance(value, list) and value else _none_value(field)
    return value


def _write_artifacts(spec_text: str, checklist: Dict[str, Any]) -> None:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    module_name = _sanitize_name(str(checklist.get("module_name", "demo_module")))
    checklist["module_name"] = module_name
    l1 = checklist.get("L1", {})
    l2 = checklist.get("L2", {})
    l3 = checklist.get("L3", {})
    l4 = checklist.get("L4", {})
    l5 = checklist.get("L5", {})

    (SPEC_DIR / "spec_input.txt").write_text(spec_text.strip() + "\n")
    (SPEC_DIR / "spec_checklist.json").write_text(json.dumps(checklist, indent=2))

    (SPEC_DIR / "L1_functional.json").write_text(json.dumps({
        "module_name": module_name,
        "behavior": _clean_text(l1.get("functional_intent", "")),
        "spec_text": spec_text,
        "reset_rules": _clean_text(l1.get("reset_rules", "")),
        "edge_cases": _clean_list(l1.get("edge_cases", [])),
    }, indent=2))

    (SPEC_DIR / "L2_interface.json").write_text(json.dumps({
        "module_name": module_name,
        "clock": _clock_reset_dict(_clean_text(l2.get("clock", ""))),
        "reset": _clock_reset_dict(_clean_text(l2.get("reset", ""))),
        "signals": _normalize_signals(l2.get("signals") or []),
        "handshake_semantics": _clean_text(l2.get("handshake_semantics", "")),
        "params_defaults": _clean_list_of_objects(l2.get("params_defaults", [])),
        "deps": [],
    }, indent=2))

    (SPEC_DIR / "L3_verification.json").write_text(json.dumps({
        "test_plan": _clean_list(l3.get("test_goals", [])),
        "oracle_plan": _clean_text(l3.get("oracle_plan", "")),
        "stimulus_strategy": _clean_text(l3.get("stimulus_strategy", "")),
        "pass_fail_criteria": _clean_text(l3.get("pass_fail_criteria", "")),
        "coverage_goals": _clean_map(l3.get("coverage_goals", {})),
    }, indent=2))

    (SPEC_DIR / "L4_architecture.json").write_text(json.dumps({
        "architecture": _clean_text(l4.get("architecture", "")),
        "clocking_cdc": _clean_text(l4.get("clocking_cdc", "")),
        "resource_choices": _clean_text(l4.get("resource_choices", "")),
        "latency_throughput": _clean_text(l4.get("latency_throughput", "")),
    }, indent=2))

    (SPEC_DIR / "L5_acceptance.json").write_text(json.dumps({
        "acceptance": _clean_text(l5.get("acceptance", "")),
        "required_artifacts": _clean_list(l5.get("required_artifacts", [])),
        "coverage_thresholds": _clean_map(l5.get("coverage_thresholds", {})),
        "exclusions_assumptions": _clean_list(l5.get("exclusions_assumptions", [])),
    }, indent=2))

    lock = {"locked_at": datetime.now(timezone.utc).isoformat(), "module_name": module_name}
    (SPEC_DIR / "lock.json").write_text(json.dumps(lock, indent=2))


def _require_gateway() -> object:
    gateway = init_llm_gateway()
    if not gateway:
        raise RuntimeError("Spec helper requires LLMs. Set USE_LLM=1 and provider keys.")
    return gateway


def _complete_checklist(
    gateway: object,
    spec_text: str,
    checklist: Dict[str, Any],
    interactive: bool,
) -> Tuple[Dict[str, Any], str]:
    checklist = update_checklist_from_spec(gateway, spec_text, checklist)
    missing = list_missing_fields(checklist)

    while missing:
        field = missing[0]
        if not interactive:
            draft = generate_field_draft(gateway, field, checklist, spec_text)
            if draft.get("value") is None:
                raise RuntimeError(f"Missing field {field.path} and no draft could be generated.")
            set_field(checklist, field.path, draft["value"])
            if draft.get("draft_text"):
                spec_text = _append_spec_notes(spec_text, f"Spec helper draft for {field.path}", draft["draft_text"])
            checklist = update_checklist_from_spec(gateway, spec_text, checklist)
            missing = list_missing_fields(checklist)
            continue

        question = generate_followup_question(gateway, field, checklist)
        print(f"\nSpec Helper: {question}")
        while True:
            try:
                answer = input("Your answer (type 'gen' to draft, 'none' if not applicable): ").strip()
            except KeyboardInterrupt:
                raise
            if not answer:
                continue
            lowered = answer.lower()
            if lowered in ("none", "n/a", "na", "not applicable"):
                set_field(checklist, field.path, _none_value(field))
                spec_text = _append_spec_notes(spec_text, f"User answered none for {field.path}", answer)
                break
            if lowered in ("gen", "g", "draft"):
                draft = generate_field_draft(gateway, field, checklist, spec_text)
                draft_text = draft.get("draft_text", "").strip()
                if draft_text:
                    print("\nDraft proposal:")
                    print(draft_text)
                else:
                    print("\nDraft proposal ready.")
                if _confirm("Accept this draft?", True):
                    value = _coerce_answer_value(field, draft.get("value"))
                    set_field(checklist, field.path, value)
                    if draft_text:
                        spec_text = _append_spec_notes(spec_text, f"Spec helper draft for {field.path}", draft_text)
                    break
                follow_up = input("Provide your answer (or type 'gen' to try again): ").strip()
                if follow_up.lower() in ("gen", "g", "draft"):
                    continue
                if not follow_up:
                    print("Missing input. Let's try again.")
                    continue
                spec_text = _append_spec_notes(spec_text, f"User answer for {field.path}", follow_up)
                break

            spec_text = _append_spec_notes(spec_text, f"User answer for {field.path}", answer)
            break

        checklist = update_checklist_from_spec(gateway, spec_text, checklist)
        missing = list_missing_fields(checklist)

    return checklist, spec_text


def collect_specs_from_text(module_name: str, spec_text: str, interactive: bool = True) -> Dict[str, Any]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    gateway = _require_gateway()
    spec_text = spec_text.strip()
    if module_name:
        spec_text = f"Module: {module_name}\n{spec_text}".strip()

    checklist = build_empty_checklist()
    if module_name:
        checklist["module_name"] = _sanitize_name(module_name)

    checklist, spec_text = _complete_checklist(gateway, spec_text, checklist, interactive=interactive)
    _write_artifacts(spec_text, checklist)
    return checklist


def collect_specs() -> None:
    _print_banner()
    gateway = _require_gateway()
    spec_text = _open_editor_for_spec()
    if not spec_text:
        print("No spec text provided; aborting.")
        return
    checklist = build_empty_checklist()
    try:
        checklist, spec_text = _complete_checklist(gateway, spec_text, checklist, interactive=True)
    except KeyboardInterrupt:
        print("\nAborted.")
        return
    _write_artifacts(spec_text, checklist)
    module_name = checklist.get("module_name", "demo_module")
    print(f"\nSpecs locked for module '{module_name}' under {SPEC_DIR}/")


if __name__ == "__main__":
    collect_specs()

__all__ = ["collect_specs", "collect_specs_from_text"]
