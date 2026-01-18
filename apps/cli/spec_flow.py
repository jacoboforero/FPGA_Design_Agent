"""
Interactive Spec Helper CLI: open an editor for the initial spec, then use
LLM-driven follow-ups to complete the L1-L5 checklist and lock the specs.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4

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
from core.schemas.specifications import (
    AcceptanceMetric,
    ArtifactRequirement,
    AssertionPlan,
    BlockDiagramNode,
    ClockDomain,
    ClockPolarity,
    ClockingInfo,
    ConfigurationParameter,
    CoverageTarget,
    DependencyEdge,
    FrozenSpecification,
    HandshakeProtocol,
    L1Specification,
    L2Specification,
    L3Specification,
    L4Specification,
    L5Specification,
    ResetConstraint,
    ResetPolarity,
    SignalDefinition,
    SignalDirection,
    SpecificationState,
    VerificationScenario,
)

SPEC_DIR = Path("artifacts/task_memory/specs")

WELCOME_BANNER = r"""
============================================================
  Multi-Agent Hardware Design CLI
============================================================
"""


def _print_banner() -> None:
    print(WELCOME_BANNER)
    print()


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


def _open_editor_for_spec() -> Tuple[str, Path]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    spec_path = SPEC_DIR / f"spec_input_{stamp}.txt"
    spec_path.write_text("")
    print("Spec Input")
    print("-" * 10)
    print("Press Enter to open your editor and paste the initial specification.")
    print("Save and close the editor when you're done.")
    print(f"File: {spec_path}")
    try:
        input()
    except KeyboardInterrupt:
        print("\nAborted.")
        return "", spec_path
    cmd = _select_editor() + [str(spec_path)]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nAborted.")
        return "", spec_path
    return spec_path.read_text().strip(), spec_path


def _append_spec_notes(spec_text: str, label: str, content: str) -> str:
    trimmed = content.strip()
    if not trimmed:
        return spec_text
    return f"{spec_text}\n\n[{label}]\n{trimmed}".strip()


def _append_spec_notes_to_file(spec_path: Path, label: str, content: str) -> None:
    trimmed = content.strip()
    if not trimmed:
        return
    existing = ""
    if spec_path.exists():
        existing = spec_path.read_text().rstrip()
    separator = "\n\n" if existing else ""
    updated = f"{existing}{separator}[{label}]\n{trimmed}\n"
    spec_path.write_text(updated)


def _format_value_for_notes(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=True)
    except TypeError:
        return str(value)


_MODULE_LINE_RE = re.compile(r"^\s*Module:\s*(\S+)\s*$", re.MULTILINE)


def _extract_module_name(spec_text: str) -> str | None:
    match = _MODULE_LINE_RE.search(spec_text)
    if not match:
        return None
    return match.group(1).strip()


def _set_module_name_in_text(spec_text: str, module_name: str) -> str:
    line = f"Module: {module_name}"
    if _MODULE_LINE_RE.search(spec_text):
        return _MODULE_LINE_RE.sub(line, spec_text, count=1)
    if not spec_text.strip():
        return line + "\n"
    return f"{line}\n{spec_text.lstrip()}"


def _set_module_name_in_file(spec_path: Path, module_name: str) -> None:
    existing = spec_path.read_text() if spec_path.exists() else ""
    spec_path.write_text(_set_module_name_in_text(existing, module_name))


def _none_value(field: FieldInfo) -> Any:
    field_type = field.field_type
    if field_type == "text":
        return "none"
    if field_type == "list":
        return ["none"]
    if field_type in ("map", "object"):
        return {"note": "none"}
    if field_type == "list_of_objects":
        keys = field.item_keys or []
        if keys:
            return [{key: "none" for key in keys}]
        return [{"note": "none"}]
    return "none"


def _is_none_token(value: str) -> bool:
    return value.strip().lower() in ("none", "n/a", "na", "not applicable")


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


def _clean_object(values: Any) -> Dict[str, Any]:
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
    if field.field_type in ("map", "object"):
        if isinstance(value, dict) and value:
            if field.path == "L3.reset_constraints":
                parsed = _as_int(value.get("min_cycles_after_reset"))
                if parsed is not None:
                    normalized = dict(value)
                    normalized["min_cycles_after_reset"] = parsed
                    return normalized
            return value
        return _none_value(field)
    if field.field_type == "list_of_objects":
        return value if isinstance(value, list) and value else _none_value(field)
    return value


def _value_missing(field: FieldInfo, value: Any) -> bool:
    field_type = field.field_type
    if field_type == "text":
        text = str(value or "").strip()
        return not text or _is_none_token(text)
    if field_type == "list":
        if not isinstance(value, list) or not value:
            return True
        for item in value:
            text = str(item).strip()
            if text and not _is_none_token(text):
                return False
        return True
    if field_type in ("map", "object"):
        if not isinstance(value, dict) or not value:
            return True
        required = field.item_keys or []
        if required:
            if field.path == "L3.reset_constraints":
                if _as_int(value.get("min_cycles_after_reset")) is None:
                    return True
            for key in required:
                if key not in value:
                    return True
                val = value.get(key)
                if isinstance(val, list):
                    if not val or all(_is_none_token(str(v).strip()) or not str(v).strip() for v in val):
                        return True
                    continue
                text = str(val or "").strip()
                if not text or _is_none_token(text):
                    return True
            return False
        return all(isinstance(v, str) and _is_none_token(v) for v in value.values())
    if field_type == "list_of_objects":
        if not isinstance(value, list) or not value:
            return True
        required = field.item_keys or []
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
                    if not val or all(_is_none_token(str(v).strip()) or not str(v).strip() for v in val):
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


def _current_user() -> str:
    return os.getenv("USER") or os.getenv("USERNAME") or "cli_user"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _require_list(values: Any, label: str) -> List[Any]:
    cleaned = _clean_list(values)
    if not cleaned:
        raise ValueError(f"Missing required list for {label}.")
    return cleaned


def _require_list_of_objects(values: Any, label: str) -> List[Dict[str, Any]]:
    cleaned = _clean_list_of_objects(values)
    if not cleaned:
        raise ValueError(f"Missing required list for {label}.")
    return cleaned


def _filter_none_list(values: List[Any]) -> List[str]:
    filtered: List[str] = []
    for item in values:
        text = str(item).strip()
        if not text or _is_none_token(text):
            continue
        filtered.append(text)
    return filtered


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "yes", "y", "1"):
        return True
    if text in ("false", "no", "n", "0"):
        return False
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, (float, int)):
        return float(value)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def _require_int(value: Any, label: str) -> int:
    parsed = _as_int(value)
    if parsed is None:
        raise ValueError(f"Missing or invalid integer for {label}.")
    return parsed


def _require_text(value: Any, label: str) -> str:
    if value is None:
        raise ValueError(f"Missing required text for {label}.")
    text = str(value).strip()
    if not text or _is_none_token(text):
        raise ValueError(f"Missing required text for {label}.")
    return text


def _normalize_operator(value: Any) -> str:
    text = str(value or "").strip()
    replacements = {
        "≥": ">=",
        "≤": "<=",
        "≠": "!=",
        "=>": ">=",
        "=<": "<=",
    }
    text = replacements.get(text, text)
    match = re.search(r"(==|!=|>=|<=|>|<)", text)
    if match:
        return match.group(1)
    return text


def _clock_polarity(value: Any) -> ClockPolarity:
    text = str(value or "").strip().lower()
    if text in ("negedge", "neg", "falling", "negative"):
        return ClockPolarity.NEGEDGE
    return ClockPolarity.POSEDGE


def _reset_polarity(value: Any) -> ResetPolarity | None:
    if value is None or _is_none_token(str(value)):
        return None
    text = str(value).strip().lower()
    if text in ("active_high", "high", "1", "true"):
        return ResetPolarity.ACTIVE_HIGH
    if text in ("active_low", "low", "0", "false"):
        return ResetPolarity.ACTIVE_LOW
    return None


def _signal_direction(value: Any) -> SignalDirection:
    text = str(value or "").strip().upper()
    if text in ("INPUT", "IN", "I"):
        return SignalDirection.INPUT
    if text in ("OUTPUT", "OUT", "O"):
        return SignalDirection.OUTPUT
    if text in ("INOUT", "IO", "BIDIR"):
        return SignalDirection.INOUT
    raise ValueError(f"Invalid signal direction: {value}")


def _write_artifacts(spec_text: str, checklist: Dict[str, Any], spec_path: Path) -> None:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    module_name = _sanitize_name(str(checklist.get("module_name", "demo_module")))
    checklist["module_name"] = module_name
    l1 = checklist.get("L1", {})
    l2 = checklist.get("L2", {})
    l3 = checklist.get("L3", {})
    l4 = checklist.get("L4", {})
    l5 = checklist.get("L5", {})

    spec_path.write_text(spec_text.strip() + "\n")
    (SPEC_DIR / "spec_checklist.json").write_text(json.dumps(checklist, indent=2))

    created_by = _current_user()
    spec_id = uuid4()
    state = SpecificationState.FROZEN
    approved_by = created_by

    l1_spec = L1Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=approved_by,
        role_summary=_require_text(l1.get("role_summary"), "L1.role_summary"),
        key_rules=_require_list(l1.get("key_rules", []), "L1.key_rules"),
        performance_intent=_require_text(l1.get("performance_intent"), "L1.performance_intent"),
        reset_semantics=_require_text(l1.get("reset_semantics"), "L1.reset_semantics"),
        corner_cases=_require_list(l1.get("corner_cases", []), "L1.corner_cases"),
        open_questions=_clean_list(l1.get("open_questions", [])),
    )

    clocking_items = _require_list_of_objects(l2.get("clocking", []), "L2.clocking")
    clocking = []
    for item in clocking_items:
        clocking.append(
            ClockingInfo(
                clock_name=_require_text(item.get("clock_name"), "L2.clocking.clock_name"),
                clock_polarity=_clock_polarity(item.get("clock_polarity")),
                reset_name=_clean_text(item.get("reset_name")) or None,
                reset_polarity=_reset_polarity(item.get("reset_polarity")),
                reset_is_async=_as_bool(item.get("reset_is_async")),
                description=_clean_text(item.get("description")) or None,
            )
        )

    signal_items = _require_list_of_objects(l2.get("signals", []), "L2.signals")
    signals = []
    for item in signal_items:
        width_expr = _require_text(item.get("width_expr"), "L2.signals.width_expr")
        signals.append(
            SignalDefinition(
                name=_require_text(item.get("name"), "L2.signals.name"),
                direction=_signal_direction(item.get("direction")),
                width_expr=width_expr,
                semantics=_clean_text(item.get("semantics")) or None,
            )
        )

    handshake_items = _clean_list_of_objects(l2.get("handshake_semantics", []))
    handshake = [
        HandshakeProtocol(
            name=_require_text(item.get("name"), "L2.handshake_semantics.name"),
            rules=_require_text(item.get("rules"), "L2.handshake_semantics.rules"),
        )
        for item in handshake_items
    ]

    params_items = _clean_list_of_objects(l2.get("configuration_parameters", []))
    params = [
        ConfigurationParameter(
            name=_require_text(item.get("name"), "L2.configuration_parameters.name"),
            default_value=_clean_text(item.get("default_value")) or None,
            description=_clean_text(item.get("description")) or None,
        )
        for item in params_items
    ]

    l2_spec = L2Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=approved_by,
        clocking=clocking,
        signals=signals,
        handshake_semantics=handshake,
        transaction_unit=_require_text(l2.get("transaction_unit"), "L2.transaction_unit"),
        configuration_parameters=params,
    )

    coverage_items = _clean_list_of_objects(l3.get("coverage_targets", []))
    coverage_targets = [
        CoverageTarget(
            coverage_id=_require_text(item.get("coverage_id"), "L3.coverage_targets.coverage_id"),
            description=_require_text(item.get("description"), "L3.coverage_targets.description"),
            metric_type=_require_text(item.get("metric_type"), "L3.coverage_targets.metric_type"),
            goal=_as_float(item.get("goal")),
            notes=_clean_text(item.get("notes")) or None,
        )
        for item in coverage_items
    ]

    reset_obj = _clean_object(l3.get("reset_constraints", {}))
    reset_constraints = ResetConstraint(
        min_cycles_after_reset=_require_int(reset_obj.get("min_cycles_after_reset"), "L3.reset_constraints.min_cycles_after_reset"),
        ordering_notes=_clean_text(reset_obj.get("ordering_notes")) or None,
    )

    scenario_items = _clean_list_of_objects(l3.get("scenarios", []))
    scenarios = [
        VerificationScenario(
            scenario_id=_require_text(item.get("scenario_id"), "L3.scenarios.scenario_id"),
            description=_require_text(item.get("description"), "L3.scenarios.description"),
            stimulus=_require_text(item.get("stimulus"), "L3.scenarios.stimulus"),
            oracle=_require_text(item.get("oracle"), "L3.scenarios.oracle"),
            pass_fail_criteria=_require_text(item.get("pass_fail_criteria"), "L3.scenarios.pass_fail_criteria"),
            illegal=bool(_as_bool(item.get("illegal")) or False),
        )
        for item in scenario_items
    ]

    l3_spec = L3Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=approved_by,
        test_goals=_require_list(l3.get("test_goals", []), "L3.test_goals"),
        oracle_strategy=_require_text(l3.get("oracle_strategy"), "L3.oracle_strategy"),
        stimulus_strategy=_require_text(l3.get("stimulus_strategy"), "L3.stimulus_strategy"),
        pass_fail_criteria=_require_list(l3.get("pass_fail_criteria", []), "L3.pass_fail_criteria"),
        coverage_targets=coverage_targets,
        reset_constraints=reset_constraints,
        scenarios=scenarios,
    )

    block_items = _require_list_of_objects(l4.get("block_diagram", []), "L4.block_diagram")
    block_diagram = []
    for item in block_items:
        interface_refs = _filter_none_list(_as_list(item.get("interface_refs", [])))
        block_diagram.append(
            BlockDiagramNode(
                node_id=_require_text(item.get("node_id"), "L4.block_diagram.node_id"),
                description=_require_text(item.get("description"), "L4.block_diagram.description"),
                node_type=_require_text(item.get("node_type"), "L4.block_diagram.node_type"),
                interface_refs=interface_refs,
                uses_standard_component=bool(_as_bool(item.get("uses_standard_component")) or False),
                notes=_clean_text(item.get("notes")) or None,
            )
        )

    dep_items = _clean_list_of_objects(l4.get("dependencies", []))
    dependencies = [
        DependencyEdge(
            parent_id=_require_text(item.get("parent_id"), "L4.dependencies.parent_id"),
            child_id=_require_text(item.get("child_id"), "L4.dependencies.child_id"),
            dependency_type=_require_text(item.get("dependency_type"), "L4.dependencies.dependency_type"),
        )
        for item in dep_items
    ]

    domain_items = _clean_list_of_objects(l4.get("clock_domains", []))
    clock_domains = [
        ClockDomain(
            name=_require_text(item.get("name"), "L4.clock_domains.name"),
            frequency_hz=_as_float(item.get("frequency_hz")),
            notes=_clean_text(item.get("notes")) or None,
        )
        for item in domain_items
    ]

    assertion_obj = _clean_object(l4.get("assertion_plan", {}))
    assertion_plan = AssertionPlan(
        sva=_filter_none_list(_as_list(assertion_obj.get("sva", []))),
        scoreboard_assertions=_filter_none_list(_as_list(assertion_obj.get("scoreboard_assertions", []))),
    )

    l4_spec = L4Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=approved_by,
        block_diagram=block_diagram,
        dependencies=dependencies,
        clock_domains=clock_domains,
        resource_strategy=_require_text(l4.get("resource_strategy"), "L4.resource_strategy"),
        latency_budget=_require_text(l4.get("latency_budget"), "L4.latency_budget"),
        assertion_plan=assertion_plan,
    )

    artifact_items = _require_list_of_objects(l5.get("required_artifacts", []), "L5.required_artifacts")
    required_artifacts = [
        ArtifactRequirement(
            name=_require_text(item.get("name"), "L5.required_artifacts.name"),
            description=_require_text(item.get("description"), "L5.required_artifacts.description"),
            mandatory=bool(_as_bool(item.get("mandatory")) if _as_bool(item.get("mandatory")) is not None else True),
        )
        for item in artifact_items
    ]

    metric_items = _require_list_of_objects(l5.get("acceptance_metrics", []), "L5.acceptance_metrics")
    acceptance_metrics = [
        AcceptanceMetric(
            metric_id=_require_text(item.get("metric_id"), "L5.acceptance_metrics.metric_id"),
            description=_require_text(item.get("description"), "L5.acceptance_metrics.description"),
            operator=_require_text(
                _normalize_operator(item.get("operator")),
                "L5.acceptance_metrics.operator",
            ),
            target_value=_require_text(item.get("target_value"), "L5.acceptance_metrics.target_value"),
            metric_source=_clean_text(item.get("metric_source")) or None,
        )
        for item in metric_items
    ]

    l5_spec = L5Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=approved_by,
        required_artifacts=required_artifacts,
        acceptance_metrics=acceptance_metrics,
        exclusions=_clean_list(l5.get("exclusions", [])),
        synthesis_target=_clean_text(l5.get("synthesis_target")) or None,
    )

    frozen = FrozenSpecification(
        spec_id=spec_id,
        l1=l1_spec,
        l2=l2_spec,
        l3=l3_spec,
        l4=l4_spec,
        l5=l5_spec,
        design_context_uri=None,
        frozen_by=created_by,
    )

    (SPEC_DIR / "L1_functional.json").write_text(json.dumps(l1_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / "L2_interface.json").write_text(json.dumps(l2_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / "L3_verification.json").write_text(json.dumps(l3_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / "L4_architecture.json").write_text(json.dumps(l4_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / "L5_acceptance.json").write_text(json.dumps(l5_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / "frozen_spec.json").write_text(json.dumps(frozen.model_dump(mode="json"), indent=2))

    lock = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "module_name": module_name,
        "spec_id": str(spec_id),
    }
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
    spec_path: Path | None = None,
) -> Tuple[Dict[str, Any], str]:
    def _load_spec_text(current: str) -> str:
        if spec_path and spec_path.exists():
            return spec_path.read_text().strip()
        return current.strip()

    def _sync_module_name_from_spec() -> None:
        if checklist.get("module_name"):
            return
        candidate = _extract_module_name(spec_text)
        if not candidate:
            return
        checklist["module_name"] = _sanitize_name(candidate)

    def _append_note(label: str, content: str) -> None:
        nonlocal spec_text
        if spec_path:
            _append_spec_notes_to_file(spec_path, label, content)
            spec_text = _load_spec_text(spec_text)
            return
        spec_text = _append_spec_notes(spec_text, label, content)

    def _thinking() -> None:
        if interactive:
            print("\nThinking...", flush=True)

    spec_text = _load_spec_text(spec_text)
    _sync_module_name_from_spec()
    _thinking()
    checklist = update_checklist_from_spec(gateway, spec_text, checklist)
    missing = list_missing_fields(checklist)

    while missing:
        field = missing[0]
        if not interactive:
            spec_text = _load_spec_text(spec_text)
            _sync_module_name_from_spec()
            _thinking()
            draft = generate_field_draft(gateway, field, checklist, spec_text)
            if draft.get("value") is None:
                raise RuntimeError(f"Missing field {field.path} and no draft could be generated.")
            value = _coerce_answer_value(field, draft.get("value"))
            if _value_missing(field, value):
                raise RuntimeError(f"Missing field {field.path} and draft was incomplete.")
            set_field(checklist, field.path, value)
            if field.path == "module_name":
                module_name = _sanitize_name(str(value))
                if spec_path:
                    _set_module_name_in_file(spec_path, module_name)
                    spec_text = _load_spec_text(spec_text)
                else:
                    spec_text = _set_module_name_in_text(spec_text, module_name)
            draft_text = draft.get("draft_text", "").strip()
            note = draft_text or _format_value_for_notes(value)
            _append_note(f"Spec helper draft for {field.path}", note)
            _thinking()
            checklist = update_checklist_from_spec(gateway, spec_text, checklist)
            missing = list_missing_fields(checklist)
            continue

        _thinking()
        question = generate_followup_question(gateway, field, checklist, spec_text)
        print(f"\nSpec Helper: {question}")
        allow_none = field.optional
        prompt = "Your answer (type 'gen' to draft"
        if allow_none:
            prompt += ", 'none' if not applicable"
        prompt += "): "
        while True:
            try:
                answer = input(prompt).strip()
            except KeyboardInterrupt:
                raise
            if not answer:
                continue
            lowered = answer.lower()
            if _is_none_token(answer):
                if not allow_none:
                    print("This field is required. Please provide a value or type 'gen' to draft.")
                    continue
                set_field(checklist, field.path, _none_value(field))
                _append_note(f"User answered none for {field.path}", answer)
                break
            if lowered in ("gen", "g", "draft"):
                _thinking()
                draft = generate_field_draft(gateway, field, checklist, spec_text)
                draft_text = draft.get("draft_text", "").strip()
                value = _coerce_answer_value(field, draft.get("value"))
                if _value_missing(field, value):
                    if draft_text:
                        print("\nDraft proposal:")
                        print(draft_text)
                    print(f"Draft is missing required structure for {field.path}. Try again or answer manually.")
                    continue
                if draft_text:
                    print("\nDraft proposal:")
                    print(draft_text)
                else:
                    print("\nDraft proposal ready.")
                if _confirm("Accept this draft?", True):
                    set_field(checklist, field.path, value)
                    if field.path == "module_name":
                        module_name = _sanitize_name(str(value))
                        if spec_path:
                            _set_module_name_in_file(spec_path, module_name)
                            spec_text = _load_spec_text(spec_text)
                        else:
                            spec_text = _set_module_name_in_text(spec_text, module_name)
                    if draft_text:
                        _append_note(f"Spec helper draft for {field.path}", draft_text)
                    else:
                        _append_note(f"Spec helper draft for {field.path}", _format_value_for_notes(value))
                    break
                follow_prompt = "Provide your answer (or type 'gen' to try again"
                if allow_none:
                    follow_prompt += ", 'none' if not applicable"
                follow_prompt += "): "
                follow_up = input(follow_prompt).strip()
                if not follow_up:
                    print("Missing input. Let's try again.")
                    continue
                if _is_none_token(follow_up):
                    if not allow_none:
                        print("This field is required. Please provide a value or type 'gen' to draft.")
                        continue
                    set_field(checklist, field.path, _none_value(field))
                    _append_note(f"User answered none for {field.path}", follow_up)
                    break
                if follow_up.lower() in ("gen", "g", "draft"):
                    continue
                if field.path == "module_name":
                    module_name = _sanitize_name(follow_up)
                    set_field(checklist, field.path, module_name)
                    if spec_path:
                        _set_module_name_in_file(spec_path, module_name)
                        spec_text = _load_spec_text(spec_text)
                    else:
                        spec_text = _set_module_name_in_text(spec_text, module_name)
                    break
                _append_note(f"User answer for {field.path}", follow_up)
                break

            if field.path == "module_name":
                module_name = _sanitize_name(answer)
                set_field(checklist, field.path, module_name)
                if spec_path:
                    _set_module_name_in_file(spec_path, module_name)
                    spec_text = _load_spec_text(spec_text)
                else:
                    spec_text = _set_module_name_in_text(spec_text, module_name)
                break
            if field.field_type == "text":
                set_field(checklist, field.path, _coerce_answer_value(field, answer))
            _append_note(f"User answer for {field.path}", answer)
            break

        spec_text = _load_spec_text(spec_text)
        _sync_module_name_from_spec()
        _thinking()
        checklist = update_checklist_from_spec(gateway, spec_text, checklist)
        missing = list_missing_fields(checklist)
        if any(item.path == field.path for item in missing):
            print(f"Still missing {field.path}. The last answer could not be applied.")

    spec_text = _load_spec_text(spec_text)
    return checklist, spec_text


def collect_specs_from_text(module_name: str, spec_text: str, interactive: bool = True) -> Dict[str, Any]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    gateway = _require_gateway()
    spec_text = spec_text.strip()
    if module_name:
        spec_text = f"Module: {module_name}\n{spec_text}".strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    spec_path = SPEC_DIR / f"spec_input_{stamp}.txt"
    spec_path.write_text(spec_text.strip() + "\n")

    checklist = build_empty_checklist()
    if module_name:
        checklist["module_name"] = _sanitize_name(module_name)

    checklist, spec_text = _complete_checklist(
        gateway,
        spec_text,
        checklist,
        interactive=interactive,
        spec_path=spec_path,
    )
    _write_artifacts(spec_text, checklist, spec_path)
    return checklist


def collect_specs() -> None:
    _print_banner()
    gateway = _require_gateway()
    spec_text, spec_path = _open_editor_for_spec()
    if not spec_text:
        print("No spec text provided; aborting.")
        return
    checklist = build_empty_checklist()
    try:
        checklist, spec_text = _complete_checklist(
            gateway,
            spec_text,
            checklist,
            interactive=True,
            spec_path=spec_path,
        )
    except KeyboardInterrupt:
        print("\nAborted.")
        return
    _write_artifacts(spec_text, checklist, spec_path)
    module_name = checklist.get("module_name", "demo_module")
    print(f"\nSpecs locked for module '{module_name}' under {SPEC_DIR}/")


if __name__ == "__main__":
    collect_specs()

__all__ = ["collect_specs", "collect_specs_from_text"]
