"""
Planner that consumes frozen spec artifacts (L1–L5) and emits design_context.json and dag.json.

Expected inputs (under artifacts/task_memory/specs/):
- L1_functional.json
- L2_interface.json
- L3_verification.json
- L4_architecture.json (optional)
- L5_acceptance.json
- lock.json (indicates specs are frozen)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

SPEC_DIR = Path("artifacts/task_memory/specs")
OUT_DIR = Path("artifacts/generated")


def _hash_dict(obj: Dict[str, Any]) -> str:
    data = json.dumps(obj, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing spec artifact: {path}")
    return json.loads(path.read_text())


def generate_from_specs(spec_dir: Path = SPEC_DIR, out_dir: Path = OUT_DIR) -> None:
    spec_dir = spec_dir.resolve()
    out_dir = out_dir.resolve()
    lock_path = spec_dir / "lock.json"
    if not lock_path.exists():
        raise RuntimeError("Specs are not locked. Run the spec helper to lock L1–L5 before planning.")

    l1 = _load_json(spec_dir / "L1_functional.json")
    l2 = _load_json(spec_dir / "L2_interface.json")
    l3 = _load_json(spec_dir / "L3_verification.json")
    l5 = _load_json(spec_dir / "L5_acceptance.json")

    module_name = l2.get("module_name") or l1.get("module_name") or "demo_module"
    rtl_file = f"rtl/{module_name}.sv"
    tb_file = f"rtl/{module_name}_tb.sv"

    interface_signals: List[Dict[str, Any]] = l2.get("signals", [])
    clocking = {
        "clk": {
            "freq_hz": l2.get("clock", {}).get("freq_hz", 100e6),
            "reset": l2.get("reset", {}).get("name", "rst_n"),
            "reset_active_low": l2.get("reset", {}).get("active_low", True),
        }
    }
    coverage_goals = l3.get("coverage_goals") or l5.get("coverage_thresholds") or {}

    nodes = {
        module_name: {
            "rtl_file": rtl_file,
            "testbench_file": tb_file,
            "interface": {"signals": interface_signals},
            "uses_library": l2.get("uses_library", []),
            "clocking": clocking,
            "coverage_goals": coverage_goals,
            "demo_behavior": l1.get("behavior", "passthrough"),
        }
    }

    design_context = {
        "design_context_hash": None,
        "nodes": nodes,
        "standard_library": l2.get("standard_library", {}),
    }
    design_context["design_context_hash"] = _hash_dict(design_context["nodes"])

    dag = {
        "nodes": [
            {
                "id": module_name,
                "type": "module",
                "deps": l2.get("deps", []),
                "state": "PENDING",
                "artifacts": {},
                "metrics": {},
            },
        ]
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "design_context.json").write_text(json.dumps(design_context, indent=2))
    (out_dir / "dag.json").write_text(json.dumps(dag, indent=2))


if __name__ == "__main__":
    generate_from_specs()
