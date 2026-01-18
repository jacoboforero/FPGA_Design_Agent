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

from core.schemas.specifications import (
    L1Specification,
    L2Specification,
    L3Specification,
    L4Specification,
    L5Specification,
)

SPEC_DIR = Path("artifacts/task_memory/specs")
OUT_DIR = Path("artifacts/generated")


def _hash_dict(obj: Dict[str, Any]) -> str:
    data = json.dumps(obj, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing spec artifact: {path}")
    return json.loads(path.read_text())


def _module_spec_paths(spec_dir: Path, module_name: str) -> Dict[str, Path]:
    suffix = f"_{module_name}.json"
    return {
        "L1": spec_dir / f"L1_functional{suffix}",
        "L2": spec_dir / f"L2_interface{suffix}",
        "L3": spec_dir / f"L3_verification{suffix}",
        "L5": spec_dir / f"L5_acceptance{suffix}",
    }


def _extract_module_nodes(l4: L4Specification, default_module: str) -> List[str]:
    if l4.block_diagram:
        nodes = [node.node_id for node in l4.block_diagram]
        return nodes or [default_module]
    return [default_module]


def _build_deps_map(
    module_nodes: List[str],
    l4: L4Specification,
) -> Dict[str, List[str]]:
    deps_map = {module: set() for module in module_nodes}
    for dep in l4.dependencies:
        parent = dep.parent_id
        child = dep.child_id
        if parent and child:
            deps_map.setdefault(child, set()).add(parent)
    for child, parents in deps_map.items():
        missing = [p for p in parents if p not in module_nodes]
        if missing:
            raise RuntimeError(f"Unknown DAG deps for {child}: {missing}")
    return {child: sorted(parents) for child, parents in deps_map.items()}


def generate_from_specs(spec_dir: Path = SPEC_DIR, out_dir: Path = OUT_DIR) -> None:
    spec_dir = spec_dir.resolve()
    out_dir = out_dir.resolve()
    lock_path = spec_dir / "lock.json"
    if not lock_path.exists():
        raise RuntimeError("Specs are not locked. Run the spec helper to lock L1–L5 before planning.")

    lock = _load_json(lock_path)
    module_name = lock.get("module_name") or "demo_module"

    l1 = L1Specification.model_validate_json((spec_dir / "L1_functional.json").read_text())
    l2 = L2Specification.model_validate_json((spec_dir / "L2_interface.json").read_text())
    l3 = L3Specification.model_validate_json((spec_dir / "L3_verification.json").read_text())
    l4 = L4Specification.model_validate_json((spec_dir / "L4_architecture.json").read_text())
    l5 = L5Specification.model_validate_json((spec_dir / "L5_acceptance.json").read_text())

    module_nodes = _extract_module_nodes(l4, module_name)
    if len(set(module_nodes)) != len(module_nodes):
        raise RuntimeError(f"Duplicate module ids in block diagram: {module_nodes}")

    l2_by_module: Dict[str, L2Specification] = {}
    l1_by_module: Dict[str, L1Specification] = {}
    l3_by_module: Dict[str, L3Specification] = {}
    l5_by_module: Dict[str, L5Specification] = {}

    for module in module_nodes:
        if module == module_name:
            l1_by_module[module] = l1
            l2_by_module[module] = l2
            l3_by_module[module] = l3
            l5_by_module[module] = l5
            continue
        paths = _module_spec_paths(spec_dir, module)
        for key, path in paths.items():
            if not path.exists():
                raise RuntimeError(f"Missing {key} spec for module '{module}': {path}")
        l1_by_module[module] = L1Specification.model_validate_json(paths["L1"].read_text())
        l2_by_module[module] = L2Specification.model_validate_json(paths["L2"].read_text())
        l3_by_module[module] = L3Specification.model_validate_json(paths["L3"].read_text())
        l5_by_module[module] = L5Specification.model_validate_json(paths["L5"].read_text())

    nodes: Dict[str, Dict[str, Any]] = {}
    for module in module_nodes:
        mod_l1 = l1_by_module[module]
        mod_l2 = l2_by_module[module]
        mod_l3 = l3_by_module[module]
        mod_l5 = l5_by_module[module]

        rtl_file = f"rtl/{module}.sv"
        tb_file = f"rtl/{module}_tb.sv"

        interface_signals: List[Dict[str, Any]] = [
            {
                "name": sig.name,
                "direction": sig.direction.value,
                "width": sig.width_expr,
                "semantics": sig.semantics,
            }
            for sig in mod_l2.signals
        ]
        clocking = [
            {
                "clock_name": clk.clock_name,
                "clock_polarity": clk.clock_polarity.value,
                "reset_name": clk.reset_name,
                "reset_polarity": clk.reset_polarity.value if clk.reset_polarity else None,
                "reset_is_async": clk.reset_is_async,
                "description": clk.description,
            }
            for clk in mod_l2.clocking
        ]
        coverage_goals = {
            target.coverage_id: target.goal
            for target in mod_l3.coverage_targets
            if target.goal is not None
        }
        verification = {
            "test_goals": mod_l3.test_goals,
            "oracle_strategy": mod_l3.oracle_strategy,
            "stimulus_strategy": mod_l3.stimulus_strategy,
            "pass_fail_criteria": mod_l3.pass_fail_criteria,
            "coverage_targets": [t.model_dump() for t in mod_l3.coverage_targets],
            "reset_constraints": mod_l3.reset_constraints.model_dump(),
        }
        acceptance = {
            "required_artifacts": [a.model_dump() for a in mod_l5.required_artifacts],
            "acceptance_metrics": [m.model_dump() for m in mod_l5.acceptance_metrics],
            "exclusions": mod_l5.exclusions,
            "synthesis_target": mod_l5.synthesis_target,
        }

        behavior_lines = [
            mod_l1.role_summary,
            f"Key rules: {', '.join(mod_l1.key_rules)}" if mod_l1.key_rules else "",
            f"Reset: {mod_l1.reset_semantics}" if mod_l1.reset_semantics else "",
            f"Corner cases: {', '.join(mod_l1.corner_cases)}" if mod_l1.corner_cases else "",
            f"Performance: {mod_l1.performance_intent}" if mod_l1.performance_intent else "",
        ]
        demo_behavior = "\n".join(line for line in behavior_lines if line)

        nodes[module] = {
            "rtl_file": rtl_file,
            "testbench_file": tb_file,
            "interface": {"signals": interface_signals},
            "uses_library": [],
            "clocking": clocking,
            "coverage_goals": coverage_goals,
            "demo_behavior": demo_behavior,
            "verification": verification,
            "acceptance": acceptance,
        }

    design_context = {
        "design_context_hash": None,
        "nodes": nodes,
        "standard_library": {},
    }
    design_context["design_context_hash"] = _hash_dict(design_context["nodes"])

    deps_map = _build_deps_map(module_nodes, l4)
    dag = {
        "nodes": [
            {
                "id": module,
                "type": "module",
                "deps": deps_map.get(module, []),
                "state": "PENDING",
                "artifacts": {},
                "metrics": {},
            }
            for module in module_nodes
        ]
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "design_context.json").write_text(json.dumps(design_context, indent=2))
    (out_dir / "dag.json").write_text(json.dumps(dag, indent=2))


if __name__ == "__main__":
    generate_from_specs()
