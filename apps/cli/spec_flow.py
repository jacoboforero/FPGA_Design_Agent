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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import UUID, uuid4

from agents.common.llm_gateway import init_llm_gateway
from agents.spec_helper.checklist import (
    FieldInfo,
    build_empty_checklist,
    list_missing_fields,
    set_field,
)
from agents.spec_helper.llm_helper import (
    generate_field_draft,
    generate_field_draft_options,
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
    Connection,
    ConnectionEndpoint,
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

# ---------------------------------------------------------------------------
# Minimal ANSI color helpers (no extra deps)
# ---------------------------------------------------------------------------


def _colors_enabled() -> bool:
    if os.getenv("CLI_COLOR", "").strip() == "0":
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    if os.getenv("FORCE_COLOR", "").strip() == "1":
        return True
    try:
        return bool(sys.stdout.isatty())
    except Exception:  # noqa: BLE001
        return False


_COLOR = _colors_enabled()

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"


def _style(text: str, *codes: str) -> str:
    if not _COLOR or not codes:
        return text
    return "".join(codes) + text + _RESET


def _print_banner() -> None:
    print(_style(WELCOME_BANNER, _BOLD, _CYAN))
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
    print("Spec Input")
    print("-" * 10)
    print("Choose how to provide the spec:")
    print("1) Create a new spec file (default)")
    print("2) Use an existing spec file (copied into a new file)")
    choice = input("Select [1/2]: ").strip().lower()
    use_existing = choice in ("2", "existing", "file", "path")

    if use_existing:
        path_text = input("Path to existing spec file: ").strip()
        if not path_text:
            print("No path provided; aborting.")
            return "", spec_path
        src_path = Path(os.path.expanduser(path_text)).expanduser()
        if not src_path.exists() or not src_path.is_file():
            print(f"Spec path not found or not a file: {src_path}")
            return "", spec_path
        try:
            spec_path.write_text(src_path.read_text())
        except Exception as exc:  # noqa: BLE001
            print(f"Could not read spec file: {exc}")
            return "", spec_path
        print("Existing spec copied into a new file for this run.")
    else:
        spec_path.write_text("")

    print("Press Enter to open your editor and paste/confirm the specification.")
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
_TOP_LINE_RE = re.compile(r"^\s*Top(?:\s+module)?:\s*(\S+)\s*$", re.MULTILINE | re.IGNORECASE)


def _extract_module_name(spec_text: str) -> str | None:
    match = _MODULE_LINE_RE.search(spec_text)
    if not match:
        return None
    return match.group(1).strip()


def _extract_top_module(spec_text: str) -> str | None:
    match = _TOP_LINE_RE.search(spec_text)
    if not match:
        return None
    return _sanitize_name(match.group(1).strip())


def _strip_top_line(text: str) -> str:
    return _TOP_LINE_RE.sub("", text).strip()


def _split_spec_modules(spec_text: str) -> tuple[str, list[tuple[str, str]]]:
    lines = spec_text.splitlines()
    module_indexes = [idx for idx, line in enumerate(lines) if _MODULE_LINE_RE.match(line)]
    if not module_indexes:
        return spec_text.strip(), []

    defaults = "\n".join(lines[: module_indexes[0]]).strip()
    modules: list[tuple[str, str]] = []
    for i, start in enumerate(module_indexes):
        end = module_indexes[i + 1] if i + 1 < len(module_indexes) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        module_name = _extract_module_name(block)
        if not module_name:
            continue
        modules.append((_sanitize_name(module_name), block))
    return defaults, modules


def _build_module_spec_text(defaults_text: str, module_text: str) -> str:
    if not defaults_text.strip():
        return module_text.strip()
    stripped_defaults = _strip_top_line(defaults_text)
    if not stripped_defaults:
        return module_text.strip()
    return (
        "Defaults (apply unless overridden by the module section):\n"
        f"{stripped_defaults.strip()}\n\n{module_text.strip()}"
    )


def _module_spec_path(base_path: Path, module_name: str) -> Path:
    stem = base_path.stem
    return base_path.with_name(f"{stem}_{_sanitize_name(module_name)}.txt")


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


def _write_artifacts(
    spec_text: str,
    checklist: Dict[str, Any],
    spec_path: Path,
    *,
    module_name: str | None = None,
    spec_id: UUID | None = None,
    filename_suffix: str = "",
) -> UUID:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    module_name = _sanitize_name(module_name or str(checklist.get("module_name", "demo_module")))
    checklist["module_name"] = module_name
    suffix = filename_suffix
    l1 = checklist.get("L1", {})
    l2 = checklist.get("L2", {})
    l3 = checklist.get("L3", {})
    l4 = checklist.get("L4", {})
    l5 = checklist.get("L5", {})

    spec_path.write_text(spec_text.strip() + "\n")
    (SPEC_DIR / f"spec_checklist{suffix}.json").write_text(json.dumps(checklist, indent=2))

    created_by = _current_user()
    spec_id = spec_id or uuid4()
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

    conn_items = _clean_list_of_objects(l4.get("connections", []))
    connections = []
    for item in conn_items:
        src_obj = _clean_object(item.get("src", {}))
        dst_obj = _clean_object(item.get("dst", {}))
        connections.append(
            Connection(
                src=ConnectionEndpoint(
                    node_id=_require_text(src_obj.get("node_id"), "L4.connections.src.node_id"),
                    port=_require_text(src_obj.get("port"), "L4.connections.src.port"),
                    slice=_clean_text(src_obj.get("slice")) or None,
                ),
                dst=ConnectionEndpoint(
                    node_id=_require_text(dst_obj.get("node_id"), "L4.connections.dst.node_id"),
                    port=_require_text(dst_obj.get("port"), "L4.connections.dst.port"),
                    slice=_clean_text(dst_obj.get("slice")) or None,
                ),
                width=_clean_text(item.get("width")) or None,
                note=_clean_text(item.get("note")) or None,
            )
        )

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
        connections=connections,
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

    (SPEC_DIR / f"L1_functional{suffix}.json").write_text(json.dumps(l1_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / f"L2_interface{suffix}.json").write_text(json.dumps(l2_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / f"L3_verification{suffix}.json").write_text(json.dumps(l3_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / f"L4_architecture{suffix}.json").write_text(json.dumps(l4_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / f"L5_acceptance{suffix}.json").write_text(json.dumps(l5_spec.model_dump(mode="json"), indent=2))
    (SPEC_DIR / f"frozen_spec{suffix}.json").write_text(json.dumps(frozen.model_dump(mode="json"), indent=2))
    return spec_id


def _write_lock(module_names: List[str], top_module: str, spec_id: UUID) -> None:
    lock = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "module_name": top_module,
        "top_module": top_module,
        "modules": module_names,
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
            print(_style("\nThinking...", _DIM), flush=True)

    def _read_multiline(prompt: str) -> str:
        print(prompt)
        print("(finish with an empty line)")
        lines: list[str] = []
        while True:
            try:
                line = input()
            except KeyboardInterrupt:
                raise
            if not line.strip():
                break
            lines.append(line.rstrip("\n"))
        return "\n".join(lines).strip()

    def _parse_list_answer(answer: str) -> List[str]:
        if not answer.strip():
            return []
        lines = [ln.strip() for ln in answer.splitlines() if ln.strip()]
        if len(lines) > 1:
            items: List[str] = []
            for ln in lines:
                if ln.startswith(("-", "•")):
                    ln = ln[1:].strip()
                if ln and not _is_none_token(ln):
                    items.append(ln)
            return items
        text = lines[0]
        if "," in text:
            parts = [p.strip() for p in text.split(",")]
            return [p for p in parts if p and not _is_none_token(p)]
        return [] if _is_none_token(text) else [text]

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

        while True:
            spec_text = _load_spec_text(spec_text)
            _sync_module_name_from_spec()
            question = generate_followup_question(gateway, field, checklist, spec_text)

            phase = field.path.split(".", 1)[0] if "." in field.path else field.path
            phase_missing = [f for f in missing if f.path == phase or f.path.startswith(f"{phase}.")]
            phase_names: List[str] = []
            for info in phase_missing[:6]:
                if "." in info.path:
                    phase_names.append(info.path.split(".", 1)[1])
                else:
                    phase_names.append(info.path)
            suffix = " ..." if len(phase_missing) > 6 else ""
            print(
                _style(
                    f"\nStatus: {len(missing)} missing fields remaining. "
                    f"Current section: {phase} ({len(phase_missing)}): {', '.join(phase_names)}{suffix}",
                    _DIM,
                )
            )

            print(f"\n{_style('Missing', _BOLD, _RED)}: {_style(field.path, _BOLD)}")
            if field.description:
                print(f"{_style('Why it matters', _YELLOW)}: {field.description}")
            if question:
                print(f"\n{_style('Spec Helper', _BLUE, _BOLD)}: {question}")

            print("\nChoose next action:")
            print(f"  {_style('1', _CYAN, _BOLD)}) Edit the spec in your editor")
            print(f"  {_style('2', _CYAN, _BOLD)}) Answer here (chat)")
            print(f"  {_style('3', _CYAN, _BOLD)}) Let the spec helper propose a draft")
            print()

            choice = input(_style("Select 1/2/3: ", _BOLD)).strip()
            if choice not in ("1", "2", "3"):
                print(_style("Please type 1, 2, or 3.", _YELLOW))
                continue

            if choice == "1":
                if not spec_path:
                    print("No spec file available to edit in this mode. Choose option 2 or 3.")
                    continue
                cmd = _select_editor() + [str(spec_path)]
                subprocess.run(cmd, check=True)
                spec_text = _load_spec_text(spec_text)
                break

            if choice == "2":
                answer = _read_multiline("Type your answer:")
                if not answer:
                    print(_style("No input received. Try again.", _YELLOW))
                    continue

                if _is_none_token(answer):
                    if not field.optional:
                        print(_style("This field is required. Provide a value, edit the spec, or choose option 3.", _YELLOW))
                        continue
                    set_field(checklist, field.path, _none_value(field))
                    _append_note(f"User answered none for {field.path}", answer)
                    break

                if field.path == "module_name":
                    module_name = _sanitize_name(answer.splitlines()[0].strip())
                    set_field(checklist, field.path, module_name)
                    if spec_path:
                        _set_module_name_in_file(spec_path, module_name)
                        spec_text = _load_spec_text(spec_text)
                    else:
                        spec_text = _set_module_name_in_text(spec_text, module_name)
                    _append_note(f"User answer for {field.path}", module_name)
                    break

                if field.field_type == "text":
                    set_field(checklist, field.path, _coerce_answer_value(field, answer))
                elif field.field_type == "list":
                    parsed = _parse_list_answer(answer)
                    if parsed:
                        set_field(checklist, field.path, parsed)

                _append_note(f"User answer for {field.path}", answer)
                break

            # choice == "3"
            _thinking()
            draft_options = generate_field_draft_options(gateway, field, checklist, spec_text, n_options=3)
            rendered: List[Tuple[str, Any]] = []
            for opt in draft_options:
                if not isinstance(opt, dict):
                    continue
                draft_text = str(opt.get("draft_text") or "").strip()
                value = _coerce_answer_value(field, opt.get("value"))
                if _value_missing(field, value):
                    continue
                note = draft_text or _format_value_for_notes(value)
                rendered.append((note, value))

            if not rendered:
                print(_style(f"Spec helper could not draft a valid proposal for {field.path}. Try option 1 or 2.", _YELLOW))
                continue

            print(_style("\nDraft options:", _MAGENTA, _BOLD))
            for idx, (note, _) in enumerate(rendered, start=1):
                print(f"  {_style(str(idx), _CYAN, _BOLD)}) {note}")
            print(f"  {_style('0', _CYAN, _BOLD)}) Reject / go back")

            selection = input(_style(f"Choose 1-{len(rendered)} to apply, or 0 to reject: ", _BOLD)).strip()
            if selection in ("0", "n", "no"):
                reason = input("Why did you reject the drafts? (optional) ").strip()
                if not reason:
                    reason = input("What should be different instead? (optional) ").strip()
                _append_note(f"User rejected draft for {field.path}", reason or "rejected")
                continue

            try:
                chosen = int(selection)
            except ValueError:
                print(_style("Please type a number.", _YELLOW))
                continue
            if chosen < 1 or chosen > len(rendered):
                print(_style("Invalid choice.", _YELLOW))
                continue

            note, value = rendered[chosen - 1]
            set_field(checklist, field.path, value)
            _append_note(f"Spec helper draft for {field.path}", note)
            if field.path == "module_name":
                module_name = _sanitize_name(str(value))
                if spec_path:
                    _set_module_name_in_file(spec_path, module_name)
                    spec_text = _load_spec_text(spec_text)
                else:
                    spec_text = _set_module_name_in_text(spec_text, module_name)
            break

        spec_text = _load_spec_text(spec_text)
        _sync_module_name_from_spec()
        _thinking()
        checklist = update_checklist_from_spec(gateway, spec_text, checklist)
        missing = list_missing_fields(checklist)
        if any(item.path == field.path for item in missing):
            print(_style(f"Still missing {field.path}. The last answer could not be applied.", _RED))

    spec_text = _load_spec_text(spec_text)
    return checklist, spec_text


def _collect_multi_specs(
    gateway: object,
    spec_text: str,
    spec_path: Path,
    interactive: bool,
) -> Dict[str, Any]:
    defaults_text, modules = _split_spec_modules(spec_text)
    if not modules:
        raise RuntimeError("Multi-spec collection called without module sections.")

    top_module = _extract_top_module(spec_text) or modules[0][0]
    module_names = [name for name, _ in modules]
    if top_module not in module_names:
        raise RuntimeError(f"Top module '{top_module}' not found in spec modules: {module_names}")
    if len(set(module_names)) != len(module_names):
        raise RuntimeError(f"Duplicate module names in spec: {module_names}")

    spec_id = uuid4()
    last_checklist: Dict[str, Any] = {}
    for module_name, module_text in modules:
        if interactive:
            print(f"\nProcessing module '{module_name}'...", flush=True)
        module_spec_text = _build_module_spec_text(defaults_text, module_text)
        module_spec_path = _module_spec_path(spec_path, module_name)
        module_spec_path.write_text(module_spec_text.strip() + "\n")

        checklist = build_empty_checklist()
        checklist["module_name"] = module_name
        checklist, module_spec_text = _complete_checklist(
            gateway,
            module_spec_text,
            checklist,
            interactive=interactive,
            spec_path=module_spec_path,
        )
        suffix = "" if module_name == top_module else f"_{module_name}"
        _write_artifacts(
            module_spec_text,
            checklist,
            module_spec_path,
            module_name=module_name,
            spec_id=spec_id,
            filename_suffix=suffix,
        )
        last_checklist = checklist

    _write_lock(module_names, top_module, spec_id)
    return last_checklist


def collect_specs_from_text(module_name: str, spec_text: str, interactive: bool = True) -> Dict[str, Any]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    gateway = _require_gateway()
    spec_text = spec_text.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    spec_path = SPEC_DIR / f"spec_input_{stamp}.txt"
    spec_path.write_text(spec_text.strip() + "\n")

    if not module_name:
        defaults_text, modules = _split_spec_modules(spec_text)
        if modules:
            return _collect_multi_specs(gateway, spec_text, spec_path, interactive)

    if module_name:
        spec_module = _extract_module_name(spec_text)
        if spec_module:
            spec_name = _sanitize_name(spec_module)
            arg_name = _sanitize_name(module_name)
            if spec_name != arg_name:
                module_name = spec_name
        spec_text = _set_module_name_in_text(spec_text, module_name)
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
    spec_id = _write_artifacts(spec_text, checklist, spec_path, module_name=checklist.get("module_name"))
    module_value = checklist.get("module_name", "demo_module")
    _write_lock([_sanitize_name(str(module_value))], _sanitize_name(str(module_value)), spec_id)
    return checklist


def collect_specs() -> None:
    _print_banner()
    gateway = _require_gateway()
    spec_text, spec_path = _open_editor_for_spec()
    if not spec_text:
        print("No spec text provided; aborting.")
        return
    defaults_text, modules = _split_spec_modules(spec_text)
    if modules:
        try:
            _collect_multi_specs(gateway, spec_text, spec_path, interactive=True)
        except KeyboardInterrupt:
            print("\nAborted.")
            return
        top_module = _extract_top_module(spec_text) or modules[0][0]
        print(
            f"\nSpecs locked for modules {', '.join(name for name, _ in modules)} "
            f"(top: {top_module}) under {SPEC_DIR}/"
        )
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
    spec_id = _write_artifacts(spec_text, checklist, spec_path, module_name=checklist.get("module_name"))
    module_name = checklist.get("module_name", "demo_module")
    _write_lock([_sanitize_name(str(module_name))], _sanitize_name(str(module_name)), spec_id)
    print(f"\nSpecs locked for module '{module_name}' under {SPEC_DIR}/")


if __name__ == "__main__":
    collect_specs()

__all__ = ["collect_specs", "collect_specs_from_text"]
