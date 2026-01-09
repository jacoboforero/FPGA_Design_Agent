"""
Interactive Spec Helper CLI: ask for a spec, surface clarifications, then write L1–L5 artifacts.
The L1–L5 checklist stays internal; the user only sees plain clarifying questions.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any, Dict, List

from agents.spec_helper.worker import SpecHelperWorker
from core.schemas.contracts import AgentType, EntityType, TaskMessage

SPEC_DIR = Path("artifacts/task_memory/specs")


def _prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{text}{suffix}: ").strip()
    return val or (default or "")


def _sanitize_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"mod_{cleaned}"
    return cleaned


def _read_spec_text() -> str:
    print("Paste your spec (plain text). Finish with a blank line:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _decode_reflections(reflections: str | None) -> Dict[str, Any]:
    if not reflections:
        return {}
    try:
        return json.loads(reflections)
    except Exception:
        return {}

def _normalize_structured(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize different field shapes from the helper into the expected keys."""
    if not data:
        return {}
    normalized = dict(data)
    if not normalized.get("signals") and normalized.get("interface_signals"):
        normalized["signals"] = normalized["interface_signals"]
    cr = normalized.get("clock_reset_details")
    if not normalized.get("clock") and isinstance(cr, dict):
        clock = cr.get("clock", {}) if isinstance(cr.get("clock"), dict) else {}
        if clock:
            normalized["clock"] = {"name": clock.get("name")}
    if not normalized.get("reset") and isinstance(cr, dict):
        reset = cr.get("reset", {}) if isinstance(cr.get("reset"), dict) else {}
        if reset:
            normalized["reset"] = {"name": reset.get("name"), "active_low": reset.get("active_level") == "low", "asynchronous": reset.get("type") == "asynchronous"}
    if not normalized.get("architecture") and normalized.get("architecture/microarchitecture"):
        normalized["architecture"] = normalized.get("architecture/microarchitecture")
    if not normalized.get("acceptance") and normalized.get("acceptance_criteria"):
        normalized["acceptance"] = normalized.get("acceptance_criteria")
    # Normalize test plan if provided as string
    if isinstance(normalized.get("test_plan"), str):
        normalized["test_plan"] = [p.strip() for p in normalized["test_plan"].replace(";", ",").split(",") if p.strip()]
    return normalized

def _prompt_signals() -> List[Dict[str, Any]]:
    sigs: List[Dict[str, Any]] = []
    print("Enter interface signals (blank name to stop). Include at least one input and one output if applicable.")
    while True:
        name = _prompt("Signal name", "")
        if not name:
            break
        direction = _prompt("Direction (INPUT/OUTPUT)", "INPUT").upper()
        width_str = _prompt("Width (e.g., 1 or 8)", "1")
        try:
            width = int(float(width_str))
        except Exception:
            width = 1
        sigs.append({"name": name, "direction": direction, "width": width})
    return sigs


def _finalize_spec(module_name: str, user_spec: Dict[str, Any], helper_structured: Dict[str, Any], interactive: bool = True) -> Dict[str, Any]:
    spec = {**user_spec, **(helper_structured or {})}
    spec["module_name"] = _sanitize_name(spec.get("module_name") or module_name)
    spec["behavior"] = spec.get("behavior") or spec.get("spec_text") or user_spec.get("spec_text", "")
    spec["spec_text"] = spec.get("spec_text") or user_spec.get("spec_text", "")

    if not spec.get("signals"):
        if not interactive:
            raise ValueError("Missing interface signals; include them in the spec text.")
        spec["signals"] = _prompt_signals()
    if spec.get("signals") is None:
        spec["signals"] = []

    if spec.get("clock") is None:
        if interactive:
            clk_name = _prompt("Clock signal name (blank if combinational)", "clk")
            spec["clock"] = {"name": clk_name} if clk_name else {}
        else:
            spec["clock"] = {}
    if spec.get("reset") is None:
        if interactive:
            rst_name = _prompt("Reset signal name (blank if none)", "rst_n")
            spec["reset"] = {"name": rst_name, "active_low": True, "asynchronous": True} if rst_name else {}
        else:
            spec["reset"] = {}

    if not spec.get("coverage_goals"):
        if interactive:
            branch_cov = _prompt("Target branch coverage (0-1)", "0.8")
            toggle_cov = _prompt("Target toggle coverage (0-1)", "0.7")
            try:
                spec["coverage_goals"] = {"branch": float(branch_cov), "toggle": float(toggle_cov)}
            except Exception:
                spec["coverage_goals"] = {"branch": 0.8, "toggle": 0.7}
        else:
            spec["coverage_goals"] = {"branch": 0.8, "toggle": 0.7}

    if spec.get("test_plan") is None:
        if interactive:
            tp = _prompt("Test plan notes (happy/reset/boundary, optional)", "")
            spec["test_plan"] = [s.strip() for s in tp.split(",") if s.strip()]
        else:
            spec["test_plan"] = []

    if not spec.get("architecture"):
        spec["architecture"] = "" if not interactive else _prompt("Architecture/microarchitecture notes (optional)", "")
    if not spec.get("acceptance"):
        spec["acceptance"] = "Tests pass and coverage meets targets" if not interactive else _prompt("Acceptance criteria (text)", "Tests pass and coverage meets targets")

    return spec


def collect_specs_from_text(module_name: str, spec_text: str, interactive: bool = True) -> Dict[str, Any]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    module_name = _sanitize_name(module_name)
    helper = SpecHelperWorker(None, Event())
    helper_structured: Dict[str, Any] = {}
    spec_payload: Dict[str, Any] = {"module_name": module_name, "spec_text": spec_text, "behavior": spec_text}

    for _ in range(3):
        payload = {**spec_payload, **helper_structured}
        msg = TaskMessage(entity_type=EntityType.REASONING, task_type=AgentType.SPECIFICATION_HELPER, context={"spec": payload})
        res = helper.handle_task(msg)
        if interactive and res.log_output:
            print(res.log_output)

        decoded = _decode_reflections(res.reflections)
        helper_structured = _normalize_structured(decoded.get("structured") or helper_structured)
        clarifications = decoded.get("clarifications") or []
        status = decoded.get("status") or ("needs_clarification" if clarifications else "complete")

        if status == "complete" and not clarifications:
            break
        if clarifications:
            if not interactive:
                raise RuntimeError(f"Spec incomplete: {clarifications}")
            print("Please answer the missing items below (press Enter to skip any):")
            answers = []
            for q in clarifications:
                ans = input(f"{q} ").strip()
                if ans:
                    answers.append(f"{q} {ans}")
            if answers:
                appended = "\n".join(answers)
                spec_payload["spec_text"] = spec_payload.get("spec_text", "") + "\n\nAdditional notes:\n" + appended
                spec_payload["behavior"] = spec_payload["spec_text"]
            else:
                break
        else:
            break

    spec = _finalize_spec(module_name, spec_payload, helper_structured, interactive=interactive)

    (SPEC_DIR / "L1_functional.json").write_text(json.dumps({
        "module_name": spec["module_name"],
        "behavior": spec.get("behavior"),
        "spec_text": spec.get("spec_text", ""),
    }, indent=2))
    (SPEC_DIR / "L2_interface.json").write_text(json.dumps({
        "module_name": spec["module_name"],
        "clock": spec.get("clock", {}),
        "reset": spec.get("reset", {}),
        "signals": spec.get("signals", []) or [],
        "deps": [],
    }, indent=2))
    (SPEC_DIR / "L3_verification.json").write_text(json.dumps({
        "coverage_goals": spec.get("coverage_goals", {}),
        "test_plan": spec.get("test_plan", []),
    }, indent=2))
    (SPEC_DIR / "L4_architecture.json").write_text(json.dumps({
        "architecture": spec.get("architecture", ""),
    }, indent=2))
    (SPEC_DIR / "L5_acceptance.json").write_text(json.dumps({
        "acceptance": spec.get("acceptance", ""),
        "coverage_thresholds": spec.get("coverage_goals", {}),
    }, indent=2))
    lock = {"locked_at": datetime.utcnow().isoformat(), "module_name": spec["module_name"]}
    (SPEC_DIR / "lock.json").write_text(json.dumps(lock, indent=2))
    if interactive:
        print(f"Specs locked for module '{spec['module_name']}' under {SPEC_DIR}/")
    return spec


def collect_specs() -> None:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    raw_module_name = _prompt("Module name", "demo_module")
    module_name = _sanitize_name(raw_module_name)
    if module_name != raw_module_name:
        print(f"Note: normalized module name to '{module_name}' for tool compatibility.")

    spec_text = _read_spec_text()
    if not spec_text:
        print("No spec text provided; aborting.")
        return

    collect_specs_from_text(module_name, spec_text, interactive=True)


if __name__ == "__main__":
    collect_specs()

__all__ = ["collect_specs", "collect_specs_from_text"]
