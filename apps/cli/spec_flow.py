"""
Interactive Spec Helper CLI: open an editor for the initial spec, then use
LLM-driven follow-ups to complete the L1-L5 checklist and lock the specs.
"""
from __future__ import annotations

import json
import os
import re
import inspect
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import UUID, uuid4

import yaml

from agents.common.llm_gateway import init_llm_gateway
from core.runtime.config import get_runtime_config
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

HOME_LOGO = [
    "   ___   _   _  _____  _____        ____   _____  _      ",
    "  / _ \\ | | | ||_   _||  _  |      |  _ \\ |_   _|| |     ",
    " / /_\\ \\| | | |  | |  | | | | _____| |_) |  | |  | |     ",
    " |  _  || |_| |  | |  | |_| ||_____| |  _<  | |  | |___ ",
    " |_| |_| \\___/   |_|  |_____|      |_| \\_\\  |_|  |_____| ",
]

_APP_TITLE = "Auto-RTL"
_APP_TAGLINE = "Design Computer Hardware, but 10x faster"

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

_CLI_THEME_ENV = "CLI_THEME"
_TERM_BG_HINT_ENV_VARS = ("TERMINAL_BACKGROUND", "TERM_BACKGROUND")

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _supports_truecolor() -> bool:
    return os.getenv("COLORTERM", "").lower() in {"truecolor", "24bit"}


def _rgb_fg(r: int, g: int, b: int, fallback: str) -> str:
    if _supports_truecolor():
        return f"\033[38;2;{r};{g};{b}m"
    return fallback


def _rgb_bg(r: int, g: int, b: int, fallback: str = "") -> str:
    if _supports_truecolor():
        return f"\033[48;2;{r};{g};{b}m"
    return fallback


def _ansi256_to_rgb(index: int) -> Tuple[int, int, int] | None:
    if index < 0 or index > 255:
        return None
    ansi16 = {
        0: (0, 0, 0),
        1: (128, 0, 0),
        2: (0, 128, 0),
        3: (128, 128, 0),
        4: (0, 0, 128),
        5: (128, 0, 128),
        6: (0, 128, 128),
        7: (192, 192, 192),
        8: (128, 128, 128),
        9: (255, 0, 0),
        10: (0, 255, 0),
        11: (255, 255, 0),
        12: (0, 0, 255),
        13: (255, 0, 255),
        14: (0, 255, 255),
        15: (255, 255, 255),
    }
    if index <= 15:
        return ansi16[index]
    if index <= 231:
        offset = index - 16
        r_idx = offset // 36
        g_idx = (offset % 36) // 6
        b_idx = offset % 6
        levels = [0, 95, 135, 175, 215, 255]
        return (levels[r_idx], levels[g_idx], levels[b_idx])
    shade = 8 + (index - 232) * 10
    return (shade, shade, shade)


def _theme_from_ansi_bg(index: int) -> str | None:
    rgb = _ansi256_to_rgb(index)
    if rgb is None:
        return None
    r, g, b = rgb
    luminance = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
    return "light" if luminance >= 128 else "dark"


def _theme_from_colorfgbg(value: str) -> str | None:
    if not value:
        return None
    # COLORFGBG commonly looks like "<fg>;<bg>".
    for token in reversed(re.split(r"[;:]", value)):
        candidate = token.strip()
        if not candidate.isdigit():
            continue
        theme = _theme_from_ansi_bg(int(candidate))
        if theme:
            return theme
    return None


def _terminal_theme_mode() -> str:
    requested = os.getenv(_CLI_THEME_ENV, "auto").strip().lower()
    if requested in {"light", "dark", "neutral"}:
        return requested

    for env_name in _TERM_BG_HINT_ENV_VARS:
        hint = os.getenv(env_name, "").strip().lower()
        if hint in {"light", "dark"}:
            return hint

    fg_bg_hint = _theme_from_colorfgbg(os.getenv("COLORFGBG", ""))
    if fg_bg_hint:
        return fg_bg_hint

    term_program = os.getenv("TERM_PROGRAM", "").strip().lower()
    # Apple Terminal defaults to a light profile on many setups.
    if term_program == "apple_terminal":
        return "light"
    # On macOS terminals without explicit color hints, avoid forcing light-on-dark
    # colors; use a neutral style that keeps terminal default foreground.
    if sys.platform == "darwin":
        return "neutral"

    return "dark"


def _build_theme(mode: str) -> Dict[str, str]:
    if mode == "neutral":
        accent = _rgb_fg(30, 146, 125, "\033[36m")
        accent_soft = _rgb_fg(84, 123, 115, "\033[36m")
        muted = _rgb_fg(96, 110, 104, "\033[90m")
        return {
            "accent": accent,
            "accent_soft": accent_soft,
            "text": "",
            "muted": muted,
            "surface": "",
            "surface_alt": "",
        }

    if mode == "light":
        accent = _rgb_fg(14, 120, 100, "\033[36m")
        accent_soft = _rgb_fg(60, 111, 98, "\033[36m")
        text = _rgb_fg(22, 31, 29, "\033[30m")
        muted = _rgb_fg(91, 109, 102, "\033[90m")
        return {
            "accent": accent,
            "accent_soft": accent_soft,
            "text": text,
            "muted": muted,
            "surface": _rgb_bg(244, 248, 246),
            "surface_alt": _rgb_bg(236, 242, 239),
        }

    accent = _rgb_fg(124, 237, 204, "\033[38;5;121m")
    accent_soft = _rgb_fg(102, 193, 166, "\033[38;5;121m")
    text = _rgb_fg(241, 248, 246, "\033[97m")
    muted = _rgb_fg(166, 197, 188, "\033[38;5;121m")
    return {
        "accent": accent,
        "accent_soft": accent_soft,
        "text": text,
        "muted": muted,
        "surface": _rgb_bg(22, 27, 28),
        "surface_alt": _rgb_bg(27, 33, 34),
    }


_THEME_MODE = _terminal_theme_mode()
_THEME = _build_theme(_THEME_MODE)

_WHITE = _THEME["text"]
_MINT = _THEME["accent"]
_RED = "\033[31m"
_GREEN = _MINT
_YELLOW = "\033[33m"
_BLUE = _MINT
_MAGENTA = _MINT
_CYAN = _MINT

_THEME_ACCENT = _THEME["accent"]
_THEME_ACCENT_SOFT = _THEME["accent_soft"]
_THEME_TEXT = _THEME["text"]
_THEME_MUTED = _THEME["muted"]
_THEME_SURFACE = _THEME["surface"]
_THEME_SURFACE_ALT = _THEME["surface_alt"]


def _style(text: str, *codes: str) -> str:
    if not _COLOR or not codes:
        return text
    active = [code for code in codes if code]
    if not active:
        return text
    return "".join(active) + text + _RESET


def _terminal_width(default: int = 108) -> int:
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
    except Exception:  # noqa: BLE001
        return default
    return max(72, min(cols, 132))


def _trim_to_width(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3].rstrip() + "..."


def _print_panel(title: str, lines: List[str], *, border_color: str = _CYAN, text_color: str = "") -> None:
    inner = min(_terminal_width() - 6, 96)
    accent = border_color or _THEME_ACCENT_SOFT
    top = "." + ("-" * (inner + 2)) + "."
    bottom = "'" + ("-" * (inner + 2)) + "'"
    print(_style(top, accent))
    header = _trim_to_width(f"[ {title} ]", inner).ljust(inner)
    print(_style("|", accent) + _style(f" {header} ", _BOLD, _THEME_TEXT, _THEME_SURFACE) + _style("|", accent))
    print(_style("|", accent) + _style(" " * (inner + 2), _THEME_SURFACE) + _style("|", accent))
    for line in lines:
        rendered = _trim_to_width(line, inner).ljust(inner)
        if text_color:
            print(_style("|", accent) + _style(f" {rendered} ", text_color, _THEME_SURFACE_ALT) + _style("|", accent))
        else:
            print(_style("|", accent) + _style(f" {rendered} ", _THEME_TEXT, _THEME_SURFACE_ALT) + _style("|", accent))
    print(_style("|", accent) + _style(" " * (inner + 2), _THEME_SURFACE) + _style("|", accent))
    print(_style(bottom, accent))
    print()


def _print_banner() -> None:
    print()
    inner = min(_terminal_width() - 6, 96)
    top = "." + ("-" * (inner + 2)) + "."
    bottom = "'" + ("-" * (inner + 2)) + "'"
    welcome = "Welcome, Vibe Engineer."
    print(_style(top, _THEME_ACCENT))
    print(_style("|", _THEME_ACCENT) + _style(f" {_trim_to_width(welcome, inner).ljust(inner)} ", _THEME_TEXT, _THEME_SURFACE) + _style("|", _THEME_ACCENT))
    print(_style(bottom, _THEME_ACCENT))
    print()
    logo_colors = (_THEME_ACCENT, _THEME_TEXT, _THEME_ACCENT, _THEME_TEXT, _THEME_ACCENT)
    for idx, line in enumerate(HOME_LOGO):
        print(_style("  " + _trim_to_width(line, inner), _BOLD, logo_colors[idx % len(logo_colors)]))
    print()
    print(_style(f"  {_APP_TAGLINE}", _THEME_MUTED))
    print(_style("  " + ("-" * min(inner, 84)), _THEME_ACCENT_SOFT))
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
    _print_panel(
        "Spec Input",
        [
            "Choose how to provide the specification source:",
            "1) Create a new spec file (default).",
            "2) Use an existing spec file (copied into a new run file).",
        ],
        border_color=_MINT,
    )
    choice = input(_style("Select option [1/2]: ", _BOLD, _MINT)).strip().lower()
    use_existing = choice in ("2", "existing", "file", "path")

    if use_existing:
        path_text = input(_style("Path to existing spec file: ", _BOLD)).strip()
        if not path_text:
            print(_style("No path provided; aborting.", _YELLOW))
            return "", spec_path
        src_path = Path(os.path.expanduser(path_text)).expanduser()
        if not src_path.exists() or not src_path.is_file():
            print(_style(f"Spec path not found or not a file: {src_path}", _RED))
            return "", spec_path
        try:
            spec_path.write_text(src_path.read_text())
        except Exception as exc:  # noqa: BLE001
            print(_style(f"Could not read spec file: {exc}", _RED))
            return "", spec_path
        print(_style("Existing spec copied into a new file for this run.", _GREEN))
    else:
        spec_path.write_text("")

    _print_panel(
        "Editor",
        [
            "Press Enter to open your editor and paste or confirm the specification.",
            "Save and close the editor to continue.",
            f"Run file: {spec_path}",
        ],
        border_color=_MINT,
    )
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


_L_SECTION_RE = re.compile(r"^\s*(L[1-5])\s*$")


def _section_key(data: Dict[str, Any], *names: str, default: Any = None) -> Any:
    for key in names:
        if key in data:
            return data[key]
    return default


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list_value(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in _as_list_value(value):
        if isinstance(item, dict):
            out.append(item)
    return out


def _as_list_of_texts(value: Any) -> List[str]:
    out: List[str] = []
    for item in _as_list_value(value):
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
            continue
        if isinstance(item, dict):
            if len(item) == 1:
                key, val = next(iter(item.items()))
                out.append(f"{str(key).strip()}: {str(val).strip()}")
            else:
                out.append(json.dumps(item, ensure_ascii=True))
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _split_l_sections(module_text: str) -> Dict[str, str]:
    lines = module_text.splitlines()
    sections: List[Tuple[str, int]] = []
    for idx, line in enumerate(lines):
        match = _L_SECTION_RE.match(line)
        if not match:
            continue
        sections.append((match.group(1), idx))

    if not sections:
        raise RuntimeError("Direct spec parsing expected L1-L5 section headers, but none were found.")

    out: Dict[str, str] = {}
    for i, (name, start_idx) in enumerate(sections):
        end_idx = sections[i + 1][1] if i + 1 < len(sections) else len(lines)
        payload = "\n".join(lines[start_idx + 1 : end_idx]).strip()
        out[name] = payload
    return out


def _yaml_escape_bullets(body: str) -> str:
    escaped: List[str] = []
    obj_item_re = re.compile(r"^(\s*)-\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*.*$")
    generic_bullet_re = re.compile(r"^(\s*)-\s+(.*)$")
    for line in body.splitlines():
        if obj_item_re.match(line):
            escaped.append(line)
            continue
        bullet = generic_bullet_re.match(line)
        if not bullet:
            escaped.append(line)
            continue
        indent, text = bullet.groups()
        quoted = text.strip().replace("\\", "\\\\").replace('"', '\\"')
        escaped.append(f'{indent}- "{quoted}"')
    return "\n".join(escaped)


def _parse_yaml_section(body: str, label: str) -> Dict[str, Any]:
    if not body.strip():
        return {}
    try:
        parsed = yaml.safe_load(body)
    except Exception as exc:  # noqa: BLE001
        try:
            parsed = yaml.safe_load(_yaml_escape_bullets(body))
        except Exception as escaped_exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to parse {label} section as YAML-like mapping: {escaped_exc}") from escaped_exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} section must parse to a mapping; got {type(parsed).__name__}.")
    return parsed


def _parse_direct_checklist(module_text: str, *, module_name_override: str | None = None) -> Dict[str, Any]:
    module_name = _extract_module_name(module_text) or module_name_override
    if not module_name:
        raise RuntimeError("Direct spec parsing requires a 'Module: <name>' line.")
    module_name = _sanitize_name(module_name)

    sections = _split_l_sections(module_text)
    missing_sections = [name for name in ("L1", "L2", "L3", "L4", "L5") if name not in sections]
    if missing_sections:
        raise RuntimeError(f"Direct spec parsing missing required sections: {', '.join(missing_sections)}")

    l1_raw = _parse_yaml_section(sections["L1"], "L1")
    l2_raw = _parse_yaml_section(sections["L2"], "L2")
    l3_raw = _parse_yaml_section(sections["L3"], "L3")
    l4_raw = _parse_yaml_section(sections["L4"], "L4")
    l5_raw = _parse_yaml_section(sections["L5"], "L5")

    reset_constraints = _as_dict(_section_key(l3_raw, "Reset constraints", "reset_constraints", default={}))
    if not reset_constraints:
        min_cycles = _section_key(l3_raw, "min_cycles_after_reset", default=None)
        ordering_notes = _section_key(l3_raw, "ordering_notes", default=None)
        if min_cycles is not None or ordering_notes is not None:
            reset_constraints = {
                "min_cycles_after_reset": min_cycles if min_cycles is not None else 0,
                "ordering_notes": ordering_notes,
            }

    assertion_plan = _as_dict(_section_key(l4_raw, "Assertion plan", "assertion_plan", default={}))
    if "sva" in l4_raw and "sva" not in assertion_plan:
        assertion_plan["sva"] = l4_raw.get("sva")
    if "scoreboard_assertions" in l4_raw and "scoreboard_assertions" not in assertion_plan:
        assertion_plan["scoreboard_assertions"] = l4_raw.get("scoreboard_assertions")
    if "sva" in assertion_plan:
        assertion_plan["sva"] = _as_list_of_texts(assertion_plan.get("sva"))
    if "scoreboard_assertions" in assertion_plan:
        assertion_plan["scoreboard_assertions"] = _as_list_of_texts(assertion_plan.get("scoreboard_assertions"))

    checklist = build_empty_checklist()
    checklist["module_name"] = module_name
    checklist["L1"] = {
        "role_summary": _section_key(l1_raw, "Role summary", "role_summary", default=""),
        "key_rules": _as_list_of_texts(_section_key(l1_raw, "Key rules", "key_rules", default=[])),
        "performance_intent": _section_key(l1_raw, "Performance intent", "performance_intent", default=""),
        "reset_semantics": _section_key(l1_raw, "Reset semantics", "reset_semantics", default=""),
        "corner_cases": _as_list_of_texts(_section_key(l1_raw, "Corner cases", "corner_cases", default=[])),
        "open_questions": _as_list_of_texts(_section_key(l1_raw, "Open questions", "open_questions", default=[])),
    }
    checklist["L2"] = {
        "clocking": _as_list_of_dicts(_section_key(l2_raw, "Clocking", "clocking", default=[])),
        "signals": _as_list_of_dicts(_section_key(l2_raw, "Signals", "signals", default=[])),
        "handshake_semantics": _as_list_of_dicts(
            _section_key(l2_raw, "Handshake semantics", "handshake_semantics", default=[])
        ),
        "transaction_unit": _section_key(l2_raw, "Transaction unit", "transaction_unit", default=""),
        "configuration_parameters": _as_list_of_dicts(
            _section_key(l2_raw, "Configuration parameters", "configuration_parameters", default=[])
        ),
    }
    checklist["L3"] = {
        "test_goals": _as_list_of_texts(_section_key(l3_raw, "Test goals", "test_goals", default=[])),
        "oracle_strategy": _section_key(l3_raw, "Oracle strategy", "oracle_strategy", default=""),
        "stimulus_strategy": _section_key(l3_raw, "Stimulus strategy", "stimulus_strategy", default=""),
        "pass_fail_criteria": _as_list_of_texts(
            _section_key(l3_raw, "Pass/fail criteria", "pass_fail_criteria", default=[])
        ),
        "coverage_targets": _as_list_of_dicts(_section_key(l3_raw, "Coverage targets", "coverage_targets", default=[])),
        "reset_constraints": reset_constraints,
        "scenarios": _as_list_of_dicts(_section_key(l3_raw, "Scenarios", "scenarios", default=[])),
    }
    checklist["L4"] = {
        "block_diagram": _as_list_of_dicts(_section_key(l4_raw, "Block diagram", "block_diagram", default=[])),
        "dependencies": _as_list_of_dicts(_section_key(l4_raw, "Dependencies", "dependencies", default=[])),
        "connections": _as_list_of_dicts(_section_key(l4_raw, "Connections", "connections", default=[])),
        "clock_domains": _as_list_of_dicts(_section_key(l4_raw, "Clock domains", "clock_domains", default=[])),
        "resource_strategy": _section_key(l4_raw, "Resource strategy", "resource_strategy", default=""),
        "latency_budget": _section_key(l4_raw, "Latency budget", "latency_budget", default=""),
        "assertion_plan": assertion_plan,
    }
    checklist["L5"] = {
        "required_artifacts": _as_list_of_dicts(_section_key(l5_raw, "Required artifacts", "required_artifacts", default=[])),
        "acceptance_metrics": _as_list_of_dicts(_section_key(l5_raw, "Acceptance metrics", "acceptance_metrics", default=[])),
        "exclusions": _as_list_of_texts(_section_key(l5_raw, "Exclusions", "exclusions", default=[])),
        "synthesis_target": _section_key(l5_raw, "Synthesis target", "synthesis_target", default=""),
    }
    return checklist


def _collect_multi_specs_direct(spec_text: str, spec_path: Path) -> Dict[str, Any]:
    _, modules = _split_spec_modules(spec_text)
    if not modules:
        raise RuntimeError("Direct multi-module parse called without Module sections.")

    top_module = _extract_top_module(spec_text) or modules[0][0]
    module_names = [name for name, _ in modules]
    if top_module not in module_names:
        raise RuntimeError(f"Top module '{top_module}' not found in spec modules: {module_names}")
    if len(set(module_names)) != len(module_names):
        raise RuntimeError(f"Duplicate module names in spec: {module_names}")

    spec_id = uuid4()
    last_checklist: Dict[str, Any] = {}
    top_checklist: Dict[str, Any] | None = None
    for module_name, module_text in modules:
        checklist = _parse_direct_checklist(module_text, module_name_override=module_name)
        module_spec_path = _module_spec_path(spec_path, module_name)
        module_spec_path.write_text(module_text.strip() + "\n")
        suffix = "" if module_name == top_module else f"_{module_name}"
        _write_artifacts(
            module_text,
            checklist,
            module_spec_path,
            module_name=module_name,
            spec_id=spec_id,
            filename_suffix=suffix,
        )
        if module_name == top_module:
            top_checklist = checklist
        last_checklist = checklist

    if top_checklist is None:
        raise RuntimeError(f"Top module '{top_module}' section was not processed.")

    canonical_modules = _validate_module_inventory(
        module_names=module_names,
        top_module=top_module,
        top_checklist=top_checklist,
    )
    _write_lock(canonical_modules, top_module, spec_id)
    return last_checklist


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

    clocking_items = _clean_list_of_objects(l2.get("clocking", []))
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


def _ordered_unique_names(values: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for raw in values:
        name = _sanitize_name(str(raw or "").strip())
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _canonical_modules_from_top_checklist(checklist: Dict[str, Any], top_module: str) -> List[str]:
    l4 = checklist.get("L4") if isinstance(checklist, dict) else None
    block_diagram = l4.get("block_diagram") if isinstance(l4, dict) else None
    block_modules: List[str] = []
    if isinstance(block_diagram, list):
        for item in block_diagram:
            if not isinstance(item, dict):
                continue
            node_id = _sanitize_name(str(item.get("node_id", "")).strip())
            if not node_id:
                continue
            is_standard = bool(_as_bool(item.get("uses_standard_component")) or False)
            if is_standard:
                continue
            block_modules.append(node_id)

    canonical = _ordered_unique_names(block_modules)
    top_module = _sanitize_name(top_module)
    if not canonical:
        return [top_module]
    if top_module in canonical:
        return [top_module] + [name for name in canonical if name != top_module]
    return [top_module] + canonical


def _validate_module_inventory(
    *,
    module_names: List[str],
    top_module: str,
    top_checklist: Dict[str, Any],
) -> List[str]:
    declared = _ordered_unique_names(module_names)
    canonical = _canonical_modules_from_top_checklist(top_checklist, top_module)
    missing = [name for name in canonical if name not in declared]
    extra = [name for name in declared if name not in canonical]
    if missing or extra:
        details: List[str] = []
        if missing:
            details.append(f"missing Module section(s): {', '.join(missing)}")
        if extra:
            details.append(f"extra Module section(s): {', '.join(extra)}")
        raise RuntimeError(
            "Spec/module mismatch between Module blocks and L4.block_diagram non-standard nodes; "
            + "; ".join(details)
            + ". Add one Module section per generated node, or mark library nodes uses_standard_component=true."
        )
    return canonical


def _ensure_single_module_contract(checklist: Dict[str, Any], module_name: str) -> None:
    canonical = _canonical_modules_from_top_checklist(checklist, module_name)
    extras = [name for name in canonical if name != _sanitize_name(module_name)]
    if extras:
        raise RuntimeError(
            "Spec defines additional generated modules in L4.block_diagram "
            f"({', '.join(extras)}) but only one Module section was provided. "
            "Use one Module: section per generated module, or mark library nodes uses_standard_component=true."
        )


def _node_meta_from_top_checklist(checklist: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    l4 = checklist.get("L4") if isinstance(checklist, dict) else None
    block_diagram = l4.get("block_diagram") if isinstance(l4, dict) else None
    if not isinstance(block_diagram, list):
        return {}
    for item in block_diagram:
        if not isinstance(item, dict):
            continue
        if _sanitize_name(str(item.get("node_id", "")).strip()) == _sanitize_name(node_id):
            return item
    return {}


def _normalize_node_type(node_meta: Dict[str, Any]) -> str:
    if not isinstance(node_meta, dict):
        return ""
    return str(node_meta.get("node_type", "")).strip().lower()


def _child_style_from_node_meta(node_meta: Dict[str, Any]) -> str:
    text = " ".join(
        [
            _normalize_node_type(node_meta),
            str(node_meta.get("description", "")).strip().lower() if isinstance(node_meta, dict) else "",
            str(node_meta.get("notes", "")).strip().lower() if isinstance(node_meta, dict) else "",
        ]
    )
    if any(token in text for token in ("comparator", "compare", "combinational", "mux", "decoder", "encoder")):
        return "combinational"
    if any(token in text for token in ("counter", "register", "sequential", "flop", "fsm", "state")):
        return "sequential"
    return "unknown"


def _width_from_top_signal(by_name: Dict[str, Dict[str, Any]], name: str, default: str = "1") -> str:
    item = by_name.get(name, {})
    value = str(item.get("width_expr", default)).strip() if isinstance(item, dict) else default
    return value or default


def _infer_child_signals_from_connections(top_checklist: Dict[str, Any], node_id: str) -> List[Dict[str, Any]]:
    l4 = top_checklist.get("L4") if isinstance(top_checklist, dict) else None
    connections = l4.get("connections") if isinstance(l4, dict) else None
    if not isinstance(connections, list):
        return []
    ports: Dict[str, str] = {}
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        src = conn.get("src") if isinstance(conn.get("src"), dict) else {}
        dst = conn.get("dst") if isinstance(conn.get("dst"), dict) else {}
        src_node = _sanitize_name(str(src.get("node_id", "")).strip()) if src else ""
        dst_node = _sanitize_name(str(dst.get("node_id", "")).strip()) if dst else ""
        if src_node == node_id:
            port = str(src.get("port", "")).strip()
            if port:
                ports.setdefault(port, "OUTPUT")
        if dst_node == node_id:
            port = str(dst.get("port", "")).strip()
            if port:
                ports.setdefault(port, "INPUT")
    l2 = top_checklist.get("L2") if isinstance(top_checklist, dict) else None
    top_signals = l2.get("signals") if isinstance(l2, dict) else None
    by_name: Dict[str, Dict[str, Any]] = {}
    if isinstance(top_signals, list):
        for sig in top_signals:
            if not isinstance(sig, dict):
                continue
            sig_name = str(sig.get("name", "")).strip()
            if sig_name:
                by_name[sig_name] = sig
    out: List[Dict[str, Any]] = []
    for name, direction in ports.items():
        out.append(
            {
                "name": name,
                "direction": direction,
                "width_expr": _width_from_top_signal(by_name, name, "1"),
                "semantics": "",
            }
        )
    return out


def _infer_child_signals_fallback(top_checklist: Dict[str, Any], node_id: str, node_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    l2 = top_checklist.get("L2") if isinstance(top_checklist, dict) else {}
    clocking = l2.get("clocking") if isinstance(l2, dict) else []
    top_signals = l2.get("signals") if isinstance(l2, dict) else []

    clk_name = "clk"
    rst_name = "rst_n"
    if isinstance(clocking, list) and clocking and isinstance(clocking[0], dict):
        clk_name = str(clocking[0].get("clock_name") or clk_name)
        rst_name = str(clocking[0].get("reset_name") or rst_name)

    by_name = {}
    if isinstance(top_signals, list):
        for sig in top_signals:
            if not isinstance(sig, dict):
                continue
            name = str(sig.get("name", "")).strip()
            if name:
                by_name[name] = sig

    def _sig(name: str, direction: str, width_expr: str = "1", semantics: str = "") -> Dict[str, Any]:
        return {"name": name, "direction": direction, "width_expr": width_expr, "semantics": semantics}

    node_style = _child_style_from_node_meta(node_meta)
    signals: List[Dict[str, Any]] = []
    if node_style != "combinational":
        signals.append(_sig(clk_name, "INPUT", "1", "clock"))
        if rst_name:
            signals.append(_sig(rst_name, "INPUT", "1", "reset"))

    lowered = node_id.lower()
    if "counter" in lowered:
        signals.append(_sig("count", "OUTPUT", _width_from_top_signal(by_name, "count_dbg", "8"), "count value"))
    elif "duty" in lowered and "reg" in lowered:
        wr_data_w = _width_from_top_signal(by_name, "wr_data", "8")
        signals.extend(
            [
                _sig("wr_en", "INPUT", "1", "write enable"),
                _sig("wr_data", "INPUT", wr_data_w, "write data"),
                _sig("duty", "OUTPUT", wr_data_w, "duty value"),
            ]
        )
    elif "compare" in lowered:
        cmp_w = _width_from_top_signal(by_name, "count_dbg", _width_from_top_signal(by_name, "duty_dbg", "8"))
        signals.extend(
            [
                _sig("count", "INPUT", cmp_w, "count input"),
                _sig("duty", "INPUT", cmp_w, "duty input"),
                _sig("pwm_out", "OUTPUT", "1", "compare output"),
            ]
        )
    return signals


def _build_autogenerated_child_checklist(top_checklist: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    checklist = build_empty_checklist()
    checklist["module_name"] = node_id
    node_meta = _node_meta_from_top_checklist(top_checklist, node_id)
    node_desc = str(node_meta.get("description", "")).strip() if isinstance(node_meta, dict) else ""
    node_type = str(node_meta.get("node_type", "")).strip() if isinstance(node_meta, dict) else ""
    node_style = _child_style_from_node_meta(node_meta)

    top_l1 = top_checklist.get("L1", {}) if isinstance(top_checklist, dict) else {}
    top_l2 = top_checklist.get("L2", {}) if isinstance(top_checklist, dict) else {}
    top_l3 = top_checklist.get("L3", {}) if isinstance(top_checklist, dict) else {}
    top_l4 = top_checklist.get("L4", {}) if isinstance(top_checklist, dict) else {}
    top_l5 = top_checklist.get("L5", {}) if isinstance(top_checklist, dict) else {}

    role_summary = node_desc or f"Auto-generated child module scaffold for {node_id}."
    key_rule = f"Implements node '{node_id}' ({node_type or 'child block'}) within the top-level architecture."
    if node_style == "combinational":
        key_rules = [
            key_rule,
            "Combinational-only contract: no edge-triggered state or internal cycle-to-cycle storage.",
        ]
        reset_semantics = "none (combinational module)"
        performance_intent = "combinational evaluation each cycle from current inputs"
    else:
        key_rules = [key_rule]
        reset_semantics = str(top_l1.get("reset_semantics", "")).strip() or "reset to deterministic safe state"
        performance_intent = str(top_l1.get("performance_intent", "")).strip() or "single-cycle operation"
    checklist["L1"] = {
        "role_summary": role_summary,
        "key_rules": key_rules,
        "performance_intent": performance_intent,
        "reset_semantics": reset_semantics,
        "corner_cases": [f"integration of {node_id} with top-level wiring"],
        "open_questions": [],
    }

    signals = _infer_child_signals_from_connections(top_checklist, node_id)
    if not signals:
        signals = _infer_child_signals_fallback(top_checklist, node_id, node_meta)
    checklist["L2"] = {
        # Keep at least one clocking entry to satisfy L2 schema requirements.
        # Combinational behavior is enforced via module_contract/style instead.
        "clocking": top_l2.get("clocking", []),
        "signals": signals,
        "handshake_semantics": top_l2.get("handshake_semantics", []),
        "transaction_unit": (
            "combinational evaluation"
            if node_style == "combinational"
            else (str(top_l2.get("transaction_unit", "")).strip() or "one update per clock edge")
        ),
        "configuration_parameters": top_l2.get("configuration_parameters", []),
    }

    checklist["L3"] = {
        "test_goals": [f"Lint/compile smoke for child module {node_id}."],
        "oracle_strategy": "basic structural/behavioral checks",
        "stimulus_strategy": "directed smoke checks",
        "pass_fail_criteria": [f"{node_id} compiles and matches its described role."],
        "coverage_targets": top_l3.get("coverage_targets", []),
        "reset_constraints": top_l3.get("reset_constraints", {"min_cycles_after_reset": 0}),
        "scenarios": [],
    }

    checklist["L4"] = {
        "block_diagram": [
            {
                "node_id": node_id,
                "description": role_summary,
                "node_type": node_type or "module",
                "interface_refs": node_meta.get("interface_refs", []) if isinstance(node_meta, dict) else [],
                "uses_standard_component": False,
                "notes": node_meta.get("notes", "") if isinstance(node_meta, dict) else "",
            }
        ],
        "dependencies": [],
        "connections": [],
        "clock_domains": top_l4.get("clock_domains", []),
        "resource_strategy": str(top_l4.get("resource_strategy", "")).strip() or "minimal child resource implementation",
        "latency_budget": str(top_l4.get("latency_budget", "")).strip() or "single-cycle",
        "assertion_plan": top_l4.get("assertion_plan", {"sva": [], "scoreboard_assertions": []}),
    }

    checklist["L5"] = {
        "required_artifacts": top_l5.get("required_artifacts", []),
        "acceptance_metrics": top_l5.get("acceptance_metrics", []),
        "exclusions": top_l5.get("exclusions", []),
        "synthesis_target": top_l5.get("synthesis_target", "fpga_generic"),
    }
    return checklist


_PROMPT_PORT_RE = re.compile(
    r"^\s*-\s*(input|output|inout)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*\(([^)]*)\))?\s*$",
    re.IGNORECASE,
)


def _prompt_width_expr(hint: str | None) -> str:
    text = str(hint or "").strip()
    if not text:
        return "1"
    num_match = re.search(r"(\d+)", text)
    if num_match:
        return str(int(num_match.group(1)))
    return "1"


def _extract_signals_from_prompt(spec_text: str) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    for line in spec_text.splitlines():
        match = _PROMPT_PORT_RE.match(line)
        if not match:
            continue
        direction_raw, name, width_hint = match.groups()
        direction = direction_raw.upper()
        signals.append(
            {
                "name": name.strip(),
                "direction": direction,
                "width_expr": _prompt_width_expr(width_hint),
                "semantics": "",
            }
        )
    return signals


def _apply_benchmark_defaults(checklist: Dict[str, Any], spec_text: str) -> Dict[str, Any]:
    module_name = checklist.get("module_name")
    if not module_name:
        extracted = _extract_module_name(spec_text) or "TopModule"
        checklist["module_name"] = _sanitize_name(extracted)
    module_name = str(checklist.get("module_name") or "TopModule")

    l1 = checklist.setdefault("L1", {})
    role_summary = str(l1.get("role_summary", "")).strip()
    if not role_summary:
        compact = " ".join(line.strip() for line in spec_text.splitlines() if line.strip())
        l1["role_summary"] = compact if compact else f"Implements module {module_name}."
    key_rules = _clean_list(l1.get("key_rules", []))
    if not key_rules:
        l1["key_rules"] = ["Implement behavior exactly as described in the prompt."]
    if not str(l1.get("performance_intent", "")).strip():
        l1["performance_intent"] = "Use prompt-defined timing/latency behavior."
    if not str(l1.get("reset_semantics", "")).strip():
        l1["reset_semantics"] = "Only as explicitly described in the prompt."
    corner_cases = _clean_list(l1.get("corner_cases", []))
    if not corner_cases:
        l1["corner_cases"] = ["No additional corner cases beyond prompt requirements."]

    l2 = checklist.setdefault("L2", {})
    signals = _clean_list_of_objects(l2.get("signals", []))
    if not signals:
        signals = _extract_signals_from_prompt(spec_text)
    if not signals:
        signals = [
            {"name": "in", "direction": "INPUT", "width_expr": "1", "semantics": ""},
            {"name": "out", "direction": "OUTPUT", "width_expr": "1", "semantics": ""},
        ]
    l2["signals"] = signals
    clocking = _clean_list_of_objects(l2.get("clocking", []))
    if not clocking:
        signal_names = {str(item.get("name", "")).lower() for item in signals if isinstance(item, dict)}
        clk_name = "clk" if "clk" in signal_names else ("clock" if "clock" in signal_names else "")
        if clk_name:
            rst_name = "rst_n" if "rst_n" in signal_names else ("reset" if "reset" in signal_names else None)
            clocking = [{"clock_name": clk_name, "clock_polarity": "POSEDGE", "reset_name": rst_name}]
        else:
            clocking = []
    l2["clocking"] = clocking
    if not str(l2.get("transaction_unit", "")).strip():
        l2["transaction_unit"] = "Prompt-defined update unit."
    if not isinstance(l2.get("handshake_semantics"), list):
        l2["handshake_semantics"] = []
    if not isinstance(l2.get("configuration_parameters"), list):
        l2["configuration_parameters"] = []

    l3 = checklist.setdefault("L3", {})
    if not _clean_list(l3.get("test_goals", [])):
        l3["test_goals"] = ["Pass benchmark harness checks for all provided tests."]
    if not str(l3.get("oracle_strategy", "")).strip():
        l3["oracle_strategy"] = "Use benchmark-provided reference outputs as oracle."
    if not str(l3.get("stimulus_strategy", "")).strip():
        l3["stimulus_strategy"] = "Use benchmark-provided test stimuli."
    if not _clean_list(l3.get("pass_fail_criteria", [])):
        l3["pass_fail_criteria"] = ["DUT outputs match oracle outputs for benchmark tests."]
    if not isinstance(l3.get("coverage_targets"), list):
        l3["coverage_targets"] = []
    reset_constraints = _clean_object(l3.get("reset_constraints", {}))
    if _as_int(reset_constraints.get("min_cycles_after_reset")) is None:
        l3["reset_constraints"] = {"min_cycles_after_reset": 0}
    if not isinstance(l3.get("scenarios"), list):
        l3["scenarios"] = []

    l4 = checklist.setdefault("L4", {})
    if not _clean_list_of_objects(l4.get("block_diagram", [])):
        l4["block_diagram"] = [
            {
                "node_id": module_name,
                "description": f"Top module for {module_name}.",
                "node_type": "module",
                "interface_refs": [],
                "uses_standard_component": False,
                "notes": "",
            }
        ]
    if not isinstance(l4.get("dependencies"), list):
        l4["dependencies"] = []
    if not isinstance(l4.get("connections"), list):
        l4["connections"] = []
    if not isinstance(l4.get("clock_domains"), list):
        l4["clock_domains"] = []
    if not str(l4.get("resource_strategy", "")).strip():
        l4["resource_strategy"] = "Use minimal resources required by the prompt behavior."
    if not str(l4.get("latency_budget", "")).strip():
        l4["latency_budget"] = "Prompt-defined latency requirements."
    assertion_plan = _clean_object(l4.get("assertion_plan", {}))
    sva_entries = _clean_list(assertion_plan.get("sva", [])) if isinstance(assertion_plan, dict) else []
    scoreboard_entries = (
        _clean_list(assertion_plan.get("scoreboard_assertions", [])) if isinstance(assertion_plan, dict) else []
    )
    if not sva_entries:
        sva_entries = ["No additional SVA beyond benchmark harness requirements."]
    if not scoreboard_entries:
        scoreboard_entries = ["Harness oracle comparison is the scoreboard authority."]
    l4["assertion_plan"] = {
        "sva": sva_entries,
        "scoreboard_assertions": scoreboard_entries,
    }

    l5 = checklist.setdefault("L5", {})
    if not _clean_list_of_objects(l5.get("required_artifacts", [])):
        l5["required_artifacts"] = [
            {"name": "rtl", "description": "Generated RTL source", "mandatory": True},
            {"name": "sim_log", "description": "Simulation log from harness", "mandatory": True},
        ]
    if not _clean_list_of_objects(l5.get("acceptance_metrics", [])):
        l5["acceptance_metrics"] = [
            {
                "metric_id": "benchmark_pass",
                "description": "All benchmark tests pass.",
                "operator": "==",
                "target_value": "1",
                "metric_source": "sim_log",
            }
        ]
    if not isinstance(l5.get("exclusions"), list):
        l5["exclusions"] = []
    if not str(l5.get("synthesis_target", "")).strip():
        l5["synthesis_target"] = "fpga_generic"
    return checklist


def _benchmark_clocking_optional(checklist: Dict[str, Any]) -> bool:
    l2 = checklist.get("L2") if isinstance(checklist.get("L2"), dict) else {}
    signals = l2.get("signals") if isinstance(l2, dict) else []
    signal_names = {str(item.get("name", "")).lower() for item in signals if isinstance(item, dict)}
    return "clk" not in signal_names and "clock" not in signal_names


def _require_gateway() -> object:
    model_override = get_runtime_config().llm.spec_helper_model
    gateway = init_llm_gateway(model_override=model_override)
    if not gateway:
        raise RuntimeError("Spec helper requires LLMs. Set USE_LLM=1 and provider keys.")
    return gateway


def _complete_checklist(
    gateway: object | None,
    spec_text: str,
    checklist: Dict[str, Any],
    interactive: bool,
    spec_path: Path | None = None,
    *,
    spec_profile: str = "engineer_fast",
    append_notes: bool = True,
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
        if not append_notes:
            return
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
    if not interactive and spec_profile == "benchmark":
        checklist = _apply_benchmark_defaults(checklist, spec_text)
        missing = list_missing_fields(checklist)
        if _benchmark_clocking_optional(checklist):
            missing = [field for field in missing if field.path != "L2.clocking"]
        if missing:
            fields = ", ".join(field.path for field in missing[:8])
            raise RuntimeError(f"Benchmark spec normalization left unresolved fields: {fields}")
        return checklist, spec_text
    _thinking()
    if gateway is None:
        raise RuntimeError("Spec helper LLM gateway unavailable for interactive/non-benchmark flow.")
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


def _invoke_complete_checklist(
    gateway: object | None,
    spec_text: str,
    checklist: Dict[str, Any],
    *,
    interactive: bool,
    spec_path: Path | None,
    spec_profile: str,
    append_notes: bool,
) -> Tuple[Dict[str, Any], str]:
    kwargs: Dict[str, Any] = {
        "interactive": interactive,
        "spec_path": spec_path,
    }
    params = inspect.signature(_complete_checklist).parameters
    if "spec_profile" in params:
        kwargs["spec_profile"] = spec_profile
    if "append_notes" in params:
        kwargs["append_notes"] = append_notes
    return _complete_checklist(
        gateway,
        spec_text,
        checklist,
        **kwargs,
    )


def _collect_multi_specs(
    gateway: object | None,
    spec_text: str,
    spec_path: Path,
    interactive: bool,
    *,
    spec_profile: str = "engineer_fast",
    append_notes: bool = True,
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
    top_checklist: Dict[str, Any] | None = None
    for module_name, module_text in modules:
        if interactive:
            print(f"\nProcessing module '{module_name}'...", flush=True)
        module_spec_text = _build_module_spec_text(defaults_text, module_text)
        module_spec_path = _module_spec_path(spec_path, module_name)
        module_spec_path.write_text(module_spec_text.strip() + "\n")

        checklist = build_empty_checklist()
        checklist["module_name"] = module_name
        checklist, module_spec_text = _invoke_complete_checklist(
            gateway,
            module_spec_text,
            checklist,
            interactive=interactive,
            spec_path=module_spec_path,
            spec_profile=spec_profile,
            append_notes=append_notes,
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
        if module_name == top_module:
            top_checklist = checklist
        last_checklist = checklist

    if top_checklist is None:
        raise RuntimeError(f"Top module '{top_module}' section was not processed.")
    lock_modules = _validate_module_inventory(
        module_names=module_names,
        top_module=top_module,
        top_checklist=top_checklist,
    )
    _write_lock(lock_modules, top_module, spec_id)
    return last_checklist


def _invoke_collect_multi_specs(
    gateway: object | None,
    spec_text: str,
    spec_path: Path,
    interactive: bool,
    *,
    spec_profile: str,
    append_notes: bool,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "interactive": interactive,
    }
    params = inspect.signature(_collect_multi_specs).parameters
    if "spec_profile" in params:
        kwargs["spec_profile"] = spec_profile
    if "append_notes" in params:
        kwargs["append_notes"] = append_notes
    return _collect_multi_specs(
        gateway,
        spec_text,
        spec_path,
        **kwargs,
    )


def collect_specs_from_text(
    module_name: str,
    spec_text: str,
    interactive: bool = True,
    spec_profile: str | None = None,
    direct_parse: bool = False,
) -> Dict[str, Any]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    spec_text = spec_text.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    spec_path = SPEC_DIR / f"spec_input_{stamp}.txt"
    spec_path.write_text(spec_text.strip() + "\n")

    _, modules = _split_spec_modules(spec_text)
    if direct_parse:
        if modules:
            return _collect_multi_specs_direct(spec_text, spec_path)
        checklist = _parse_direct_checklist(spec_text, module_name_override=module_name or None)
        _ensure_single_module_contract(checklist, checklist.get("module_name", module_name or "demo_module"))
        spec_id = _write_artifacts(spec_text, checklist, spec_path, module_name=checklist.get("module_name"))
        module_value = checklist.get("module_name", "demo_module")
        _write_lock([_sanitize_name(str(module_value))], _sanitize_name(str(module_value)), spec_id)
        return checklist

    profile = spec_profile or get_runtime_config().resolved_preset.spec_profile
    benchmark_mode = profile == "benchmark"
    gateway = None if benchmark_mode else _require_gateway()
    interactive = interactive and not benchmark_mode
    append_notes = not benchmark_mode

    if modules:
        return _invoke_collect_multi_specs(
            gateway,
            spec_text,
            spec_path,
            interactive,
            spec_profile=profile,
            append_notes=append_notes,
        )

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

    checklist, spec_text = _invoke_complete_checklist(
        gateway,
        spec_text,
        checklist,
        interactive=interactive,
        spec_path=spec_path,
        spec_profile=profile,
        append_notes=append_notes,
    )
    _ensure_single_module_contract(checklist, checklist.get("module_name", module_name or "demo_module"))
    spec_id = _write_artifacts(spec_text, checklist, spec_path, module_name=checklist.get("module_name"))
    module_value = checklist.get("module_name", "demo_module")
    _write_lock([_sanitize_name(str(module_value))], _sanitize_name(str(module_value)), spec_id)
    return checklist


def collect_specs() -> None:
    _print_banner()
    profile = get_runtime_config().resolved_preset.spec_profile
    benchmark_mode = profile == "benchmark"
    gateway = None if benchmark_mode else _require_gateway()
    spec_text, spec_path = _open_editor_for_spec()
    if not spec_text:
        print("No spec text provided; aborting.")
        return
    defaults_text, modules = _split_spec_modules(spec_text)
    if modules:
        try:
            _invoke_collect_multi_specs(
                gateway,
                spec_text,
                spec_path,
                interactive=not benchmark_mode,
                spec_profile=profile,
                append_notes=not benchmark_mode,
            )
        except KeyboardInterrupt:
            print("\nAborted.")
            return
        top_module = _extract_top_module(spec_text) or modules[0][0]
        lock_modules = [name for name, _ in modules]
        lock_path = SPEC_DIR / "lock.json"
        if lock_path.exists():
            try:
                lock_payload = json.loads(lock_path.read_text())
                values = lock_payload.get("modules")
                if isinstance(values, list):
                    parsed = _ordered_unique_names([str(v) for v in values])
                    if parsed:
                        lock_modules = parsed
            except Exception:
                pass
        print(
            f"\nSpecs locked for modules {', '.join(lock_modules)} "
            f"(top: {top_module}) under {SPEC_DIR}/"
        )
        return

    checklist = build_empty_checklist()
    try:
        checklist, spec_text = _invoke_complete_checklist(
            gateway,
            spec_text,
            checklist,
            interactive=not benchmark_mode,
            spec_path=spec_path,
            spec_profile=profile,
            append_notes=not benchmark_mode,
        )
    except KeyboardInterrupt:
        print("\nAborted.")
        return
    _ensure_single_module_contract(checklist, checklist.get("module_name", "demo_module"))
    spec_id = _write_artifacts(spec_text, checklist, spec_path, module_name=checklist.get("module_name"))
    module_name = checklist.get("module_name", "demo_module")
    _write_lock([_sanitize_name(str(module_name))], _sanitize_name(str(module_name)), spec_id)
    print(f"\nSpecs locked for module '{module_name}' under {SPEC_DIR}/")


if __name__ == "__main__":
    collect_specs()

__all__ = ["collect_specs", "collect_specs_from_text"]
