"""
Interactive Spec Helper CLI: ask for a spec, surface clarifications, then write L1–L5 artifacts.
The L1–L5 checklist stays internal; the user only sees plain clarifying questions.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any, Dict, List
import shutil

from agents.spec_helper.worker import SpecHelperWorker
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from core.schemas.contracts import AgentType, EntityType, TaskMessage, TaskStatus

SPEC_DIR = Path("artifacts/task_memory/specs")
SAMPLES_DIR = Path("artifacts/specs/smoke")
SYSTEM_SPEC_DIR = Path("artifacts/task_memory/system_specs")

LOGO = r"""
__        __   _                            _ 
\ \      / /__| | ___ ___  _ __ ___   ___  | |
 \ \ /\ / / _ \ |/ __/ _ \| '_ ` _ \ / _ \ | |
  \ V  V /  __/ | (_| (_) | | | | | |  __/ |_|
   \_/\_/ \___|_|\___\___/|_| |_| |_|\___| (_)
"""

def _prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{text}{suffix}: ").strip()
    return val or (default or "")


def _sanitize_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"mod_{cleaned}"
    return cleaned


def _create_scratch_file(prefix: str, content: str = "") -> Path:
    scratch_dir = Path("artifacts/specs/scratch")
    scratch_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = scratch_dir / f"{prefix}_{ts}.txt"
    path.write_text(content)
    return path


def _open_in_editor(path: Path) -> None:
    editor = os.getenv("EDITOR", "nano")
    cmd = shlex.split(editor) + [str(path)]
    try:
        subprocess.run(cmd, check=False)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to open editor '{editor}': {exc}") from exc


def _append_clarifications(path: Path, clarifications: List[str], answers: List[str]) -> None:
    with path.open("a") as f:
        f.write("\n\n### Clarifications\n")
        for q, a in zip(clarifications, answers):
            f.write(f"- {q}\n  Answer: {a}\n")


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


def _guess_module_name(spec_text: str) -> str:
    for line in spec_text.splitlines():
        low = line.lower().strip()
        if low.startswith("module:"):
            return line.split(":", 1)[1].strip()
    return ""


def _llm_system_decompose(system_spec: str) -> List[Dict[str, Any]]:
    gateway = init_llm_gateway()
    if not gateway or not Message:
        raise RuntimeError("LLM gateway not available; cannot decompose system spec.")
    system_prompt = (
        "You are a hardware architect. Given a system-level hardware spec, propose a set of modules.\n"
        "Return JSON ONLY with key 'modules': list of {name, role, interfaces (free-text), clock_domain, reset, type ('ip' or 'custom'), notes}.\n"
        "Do not include code fences or prose."
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content=system_prompt),
        Message(role=MessageRole.USER, content=system_spec),
    ]
    cfg = GenerationConfig(max_tokens=800, temperature=0.3)
    import asyncio

    resp = asyncio.run(gateway.generate(messages=messages, config=cfg))  # type: ignore[arg-type]
    try:
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.strip("`")
        data = json.loads(content)
        modules = data.get("modules", [])
        # Filter out malformed entries and ensure each is a dict.
        return [m for m in modules if isinstance(m, dict)]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to parse module decomposition: {exc}")


def _print_welcome() -> bool:
    print(LOGO)
    print("Press Enter to open the editor and provide your spec:")
    try:
        input()
        return True
    except KeyboardInterrupt:
        return False

def _finalize_spec(module_name: str | None, user_spec: Dict[str, Any], helper_structured: Dict[str, Any], interactive: bool = True) -> Dict[str, Any]:
    # Merge user payload and LLM-extracted structured data
    merged = {**user_spec, **(helper_structured or {})}
    # Choose module name: prefer LLM extraction, then provided, else fallback
    chosen_module = merged.get("module_name") or module_name or "my_module"
    merged["module_name"] = _sanitize_name(chosen_module)
    merged["spec_text"] = merged.get("spec_text") or user_spec.get("spec_text", "")
    merged["behavior"] = merged.get("behavior") or merged["spec_text"]

    # Signals
    merged["signals"] = merged.get("signals") or []

    # Coverage/test plan/architecture/acceptance defaults if still missing
    merged["coverage_goals"] = merged.get("coverage_goals") or {}
    if isinstance(merged.get("test_plan"), str):
        merged["test_plan"] = [s.strip() for s in merged["test_plan"].replace(";", ",").split(",") if s.strip()]
    merged["test_plan"] = merged.get("test_plan") or []
    merged["architecture"] = merged.get("architecture") or ""
    merged["acceptance"] = merged.get("acceptance") or "Tests pass and coverage meets targets"

    return merged


def collect_specs_from_text(module_name: str | None, spec_text: str, interactive: bool = True) -> Dict[str, Any]:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    helper = SpecHelperWorker(None, Event())
    helper_structured: Dict[str, Any] = {}
    spec_payload: Dict[str, Any] = {"module_name": module_name or "", "spec_text": spec_text, "behavior": spec_text}
    scratch_path = _create_scratch_file(module_name or "module", spec_text)

    def _has_required(data: Dict[str, Any]) -> bool:
        if not data.get("module_name"):
            return False
        sigs = data.get("signals") or []
        if not sigs:
            return False
        clk = data.get("clock")
        rst = data.get("reset")
        if not clk and not rst:
            return False
        return True

    def _manual_fill(data: Dict[str, Any]) -> Dict[str, Any]:
        print("Enter interface signals as 'name,direction,width' (direction INPUT/OUTPUT). Blank to finish.")
        signals = []
        while True:
            line = input("signal> ").strip()
            if not line:
                break
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                print("Need at least name,direction.")
                continue
            name, direction = parts[0], parts[1].upper()
            width = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            signals.append({"name": name, "direction": direction, "width": width})
        clk_name = input("Clock name (blank if none): ").strip()
        rst_name = input("Reset name (blank if none): ").strip()
        rst_active_low = input("Reset active low? [Y/n]: ").strip().lower()
        rst_async = input("Reset asynchronous? [Y/n]: ").strip().lower()
        data = dict(data)
        if signals:
            data["signals"] = signals
        if clk_name:
            data["clock"] = {"name": clk_name}
        if rst_name:
            data["reset"] = {"name": rst_name, "active_low": rst_active_low != "n", "asynchronous": rst_async != "n"}
        return data

    def _draft_interface(data: Dict[str, Any]) -> Dict[str, Any]:
        if not helper.gateway or not Message:
            raise RuntimeError("LLM gateway unavailable to draft interface.")
        prompt = (
            "Draft a minimal interface JSON for the module based on the spec text.\n"
            "Return JSON ONLY with keys: module_name, signals (list of {name,direction,width}), "
            "clock {name} if sequential else {}, reset {name, active_low, asynchronous} if present."
        )
        msgs = [
            Message(role=MessageRole.SYSTEM, content=prompt),
            Message(role=MessageRole.USER, content=data.get("spec_text", "")),
        ]
        cfg = GenerationConfig(max_tokens=300, temperature=0.2, stop_sequences=["```", "\n\n"])
        import asyncio

        resp = asyncio.run(helper.gateway.generate(messages=msgs, config=cfg))  # type: ignore[arg-type]
        raw = resp.content.strip().strip("`")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                parsed = parsed[0]
            if not isinstance(parsed, dict):
                raise ValueError("Not a JSON object")
            merged = dict(data)
            merged.update({k: v for k, v in parsed.items() if k in ("signals", "clock", "reset", "module_name")})
            return merged
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to draft interface from LLM: {exc}") from exc

    for _ in range(3):
        payload = {**spec_payload, **helper_structured}
        msg = TaskMessage(entity_type=EntityType.REASONING, task_type=AgentType.SPECIFICATION_HELPER, context={"spec": payload})
        res = helper.handle_task(msg)
        if interactive and res.log_output:
            print(res.log_output)

        decoded = _decode_reflections(res.reflections) or {}
        helper_structured = _normalize_structured(decoded.get("structured") or {}) or {}
        clarifications = decoded.get("clarifications") or []
        status = decoded.get("status") or ("needs_clarification" if clarifications else "complete")

        if res.status != TaskStatus.SUCCESS:
            raise RuntimeError(f"Spec helper failed for {module_name}: {res.log_output or res.status}")

        if status == "invalid":
            if not interactive:
                raise RuntimeError("Spec invalid/unrelated to hardware.")
            print(f"Spec looks invalid or unrelated to hardware. Please edit the spec file and save it: {scratch_path}")
            _open_in_editor(scratch_path)
            spec_payload["spec_text"] = scratch_path.read_text()
            spec_payload["behavior"] = spec_payload["spec_text"]
            continue

        needs_retry = False

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
                _append_clarifications(scratch_path, clarifications, answers)
                spec_payload["spec_text"] = scratch_path.read_text()
                spec_payload["behavior"] = spec_payload["spec_text"]
                needs_retry = True

        if not _has_required(helper_structured):
            if not interactive:
                raise RuntimeError("Spec missing required interface fields (signals and clock/reset).")
            missing_notes = []
            if not (helper_structured.get("signals") or []):
                missing_notes.append("signals (name, direction, width)")
            if not (helper_structured.get("clock") or helper_structured.get("reset")):
                missing_notes.append("clock/reset")
            print(f"Required fields missing: {', '.join(missing_notes)}.")
            choice = input("Provide now (p), let helper draft (d), or abort (q)? [p/d/q]: ").strip().lower()
            if choice == "q":
                raise RuntimeError("Spec locking aborted due to missing required fields.")
            if choice == "d":
                helper_structured = _draft_interface(helper_structured)
            else:
                helper_structured = _manual_fill(helper_structured)
            needs_retry = False  # We now have required fields; allow exit.

        if not needs_retry and _has_required(helper_structured) and status == "complete":
            break

    if not _has_required(helper_structured):
        raise RuntimeError("Failed to lock spec: required interface fields (signals and clock/reset) are still missing.")

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
    if not _print_welcome():
        print("\nCancelled by user.")
        return
    scratch = _create_scratch_file("spec")
    print(f"Spec file created at: {scratch}")
    input("Press Enter to open the editor for the spec (Ctrl+C to abort)...")
    _open_in_editor(scratch)
    spec_text = scratch.read_text().strip()
    if not spec_text:
        print("No spec text provided; aborting.")
        return
    guessed = _guess_module_name(spec_text) or "my_module"
    raw_module_name = _prompt("Module name (used for artifacts; press Enter to use spec's module)", guessed)
    module_name = _sanitize_name(raw_module_name) if raw_module_name else _sanitize_name(guessed)
    if module_name != raw_module_name and raw_module_name:
        print(f"Note: normalized module name to '{module_name}' for tool compatibility.")

    collect_specs_from_text(module_name, spec_text, interactive=True)


def collect_system_specs(copy_primary: bool = False) -> Dict[str, Any]:
    """
    System-level flow: take a high-level spec, decompose into modules via LLM,
    run spec helper per module, and store specs under artifacts/task_memory/system_specs/{module}.
    Optionally copies the selected primary module into the standard SPEC_DIR for single-node compatibility.
    """
    SYSTEM_SPEC_DIR.mkdir(parents=True, exist_ok=True)
    if not _print_welcome():
        print("\nCancelled by user.")
        return
    system_scratch = _create_scratch_file("system_spec")
    print(f"System spec file created at: {system_scratch}")
    input("Press Enter to open the editor for the system spec (Ctrl+C to abort)...")
    _open_in_editor(system_scratch)
    system_spec = system_scratch.read_text().strip()
    if not system_spec:
        print("No system spec provided; aborting.")
        return

    try:
        modules = _llm_system_decompose(system_spec)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to decompose system spec: {exc}")
        return

    if not modules:
        print("No modules proposed by the LLM; please provide a clearer system spec.")
        return

    print("Proposed modules:")
    for idx, m in enumerate(modules):
        name = m.get("name", "unnamed") if isinstance(m, dict) else "unnamed"
        role = m.get("role", "") if isinstance(m, dict) else ""
        print(f"  [{idx}] {name} - {role}")
    primary_idx = _prompt("Select primary module index for execution", "0")
    try:
        primary_idx_int = int(primary_idx)
    except Exception:
        primary_idx_int = 0
    if primary_idx_int < 0 or primary_idx_int >= len(modules):
        primary_idx_int = 0
    primary_module = modules[primary_idx_int].get("name", "top") if isinstance(modules[primary_idx_int], dict) else "top"

    # Generate per-module specs via LLM (draft) then feed through spec helper to lock
    gateway = init_llm_gateway()
    if not gateway or not Message:
        print("LLM gateway not available; cannot draft per-module specs.")
        return

    draft_prompt = (
        "You are drafting a module-level hardware spec from a system spec.\n"
        "Given the system spec and the module info, produce a concise module spec including:\n"
        "Module: <name>\nSignals: list ports with direction/width\nClock/Reset if needed\nBehavior\nVerification\nCoverage goals\nArchitecture\nAcceptance\nReturn plain text, no code fences."
    )
    failed_modules: List[str] = []
    locked_modules: List[str] = []
    for idx, m in enumerate(modules):
        if not isinstance(m, dict):
            continue
        mod_name = m.get("name") or f"module_{idx}"
        mod_role = m.get("role", "")
        user_content = f"System spec:\n{system_spec}\n\nModule info:\n{json.dumps(m, indent=2)}"
        messages = [
            Message(role=MessageRole.SYSTEM, content=draft_prompt),
            Message(role=MessageRole.USER, content=user_content),
        ]
        cfg = GenerationConfig(max_tokens=800, temperature=0.3)
        import asyncio
        resp = asyncio.run(gateway.generate(messages=messages, config=cfg))  # type: ignore[arg-type]
        draft_spec = resp.content
        # Lock via spec helper (non-interactive unless clarifications needed)
        print(f"\n--- Drafting and locking spec for {mod_name} ---")
        try:
            # Start from drafted spec in a scratch file for user edits.
            module_scratch = _create_scratch_file(mod_name, draft_spec)
            print(f"Module spec file created at: {module_scratch}")
            input("Press Enter to open the editor for this module spec (Ctrl+C to abort)...")
            _open_in_editor(module_scratch)
            edited_spec = module_scratch.read_text()
            # Lock specs to the standard SPEC_DIR, then copy to module-specific dir and clear for next.
            # Always interactive to let the LLM ask clarifications per module.
            collect_specs_from_text(mod_name, edited_spec, interactive=True)
            out_dir = SYSTEM_SPEC_DIR / mod_name
            if out_dir.exists():
                shutil.rmtree(out_dir)
            shutil.copytree(SPEC_DIR, out_dir)
            (out_dir / "draft_spec.txt").write_text(edited_spec)
            shutil.rmtree(SPEC_DIR)
            locked_modules.append(mod_name)
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to lock spec for {mod_name}: {exc}")
            failed_modules.append(mod_name)
            if SPEC_DIR.exists():
                shutil.rmtree(SPEC_DIR)
            # Abort further modules on failure
            break

    if failed_modules:
        print(f"Failed modules: {', '.join(failed_modules)}. Aborting before planning.")
        return {"modules": [m for m in modules if isinstance(m, dict) and m.get('name') not in failed_modules], "primary_module": None, "failed_modules": failed_modules, "aborted": True}

    # Copy primary module specs back into SPEC_DIR only if requested for legacy single-node runs.
    if copy_primary and primary_module:
        primary_dir = SYSTEM_SPEC_DIR / primary_module
        if SPEC_DIR.exists():
            shutil.rmtree(SPEC_DIR)
        shutil.copytree(primary_dir, SPEC_DIR)
        print(f"Primary module for execution: {primary_module}. Specs locked under {SPEC_DIR}.")
    else:
        # Ensure the single-node spec dir is cleared so downstream planning uses system_specs.
        if SPEC_DIR.exists():
            shutil.rmtree(SPEC_DIR)
        if primary_module:
            print(f"Specs locked for modules under {SYSTEM_SPEC_DIR}. Primary selection: {primary_module}.")
        else:
            print(f"Specs locked for modules under {SYSTEM_SPEC_DIR}. No primary module selected.")

    return {"modules": modules, "primary_module": primary_module}

if __name__ == "__main__":
    collect_specs()

__all__ = ["collect_specs", "collect_specs_from_text", "collect_system_specs"]
