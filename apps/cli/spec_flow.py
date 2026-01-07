"""
Interactive Spec Helper CLI: collect L1–L5 specs, write artifacts, and lock them.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SPEC_DIR = Path("artifacts/task_memory/specs")


def _prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{text}{suffix}: ").strip()
    return val or (default or "")


def _prompt_yes_no(text: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    val = input(f"{text}{suffix}: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def collect_specs() -> None:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    module_name = _prompt("Module name", "demo_module")
    behavior = _prompt("Behavior summary", "passthrough")
    perf = _prompt("Performance/latency goal", "none")

    clk = _prompt("Clock name", "clk")
    freq = _prompt("Clock frequency (Hz)", "100e6")
    rst = _prompt("Reset name", "rst_n")
    rst_low = _prompt_yes_no("Reset active low?", True)

    signals = []
    print("Enter interface signals (blank name to stop).")
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
        signals.append({"name": name, "direction": direction, "width": width})

    if not signals:
        signals = [
            {"name": "in_data", "direction": "INPUT", "width": 8},
            {"name": "out_data", "direction": "OUTPUT", "width": 8},
        ]

    branch_cov = _prompt("Target branch coverage (0-1)", "0.8")
    toggle_cov = _prompt("Target toggle coverage (0-1)", "0.7")

    scenarios = _prompt("Test scenarios (comma-separated)", "happy,reset,boundary")
    acceptance = _prompt("Acceptance criteria (text)", "Tests pass and coverage meets targets")

    l1 = {
        "module_name": module_name,
        "behavior": behavior,
        "performance": perf,
    }
    l2 = {
        "module_name": module_name,
        "clock": {"name": clk, "freq_hz": float(freq)},
        "reset": {"name": rst, "active_low": rst_low},
        "signals": signals,
    }
    l3 = {
        "coverage_goals": {"branch": float(branch_cov), "toggle": float(toggle_cov)},
        "test_plan": [s.strip() for s in scenarios.split(",") if s.strip()],
    }
    l4 = {"architecture": "TBD", "notes": ""}
    l5 = {
        "acceptance": acceptance,
        "coverage_thresholds": {"branch": float(branch_cov), "toggle": float(toggle_cov)},
    }

    (SPEC_DIR / "L1_functional.json").write_text(json.dumps(l1, indent=2))
    (SPEC_DIR / "L2_interface.json").write_text(json.dumps(l2, indent=2))
    (SPEC_DIR / "L3_verification.json").write_text(json.dumps(l3, indent=2))
    (SPEC_DIR / "L4_architecture.json").write_text(json.dumps(l4, indent=2))
    (SPEC_DIR / "L5_acceptance.json").write_text(json.dumps(l5, indent=2))
    lock = {"locked_at": datetime.utcnow().isoformat(), "module_name": module_name}
    (SPEC_DIR / "lock.json").write_text(json.dumps(lock, indent=2))
    print(f"Specs locked for module '{module_name}' under {SPEC_DIR}/")


if __name__ == "__main__":
    collect_specs()
