"""
Planner that consumes planning_spec.json and emits design_context.json and dag.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from core.schemas.planning_spec import PlanningSpec
from core.schemas.specifications import (
    AcceptanceMetric,
    ArtifactRequirement,
    AssertionPlan,
    BlockDiagramNode,
    ClockDomain,
    ClockPolarity,
    ClockingInfo,
    ConfigurationParameter,
    Connection,
    ConnectionEndpoint,
    CoverageTarget,
    DependencyEdge,
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
from core.runtime.testbench_contract import build_testbench_contract
from orchestrator.preplan_validator import ValidationIssue, validate_preplan_inputs

SPEC_DIR = Path("artifacts/task_memory/specs")
OUT_DIR = Path("artifacts/generated")


def _hash_dict(obj: Dict[str, Any]) -> str:
    data = json.dumps(obj, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:16]

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing spec artifact: {path}")
    return json.loads(path.read_text())

def _planning_spec_path(spec_dir: Path) -> Path:
    return spec_dir / "planning_spec.json"


def _load_planning_spec(spec_dir: Path) -> PlanningSpec:
    path = _planning_spec_path(spec_dir)
    if not path.exists():
        raise RuntimeError("Missing planning_spec.json. Run the spec helper before planning.")
    return PlanningSpec.model_validate_json(path.read_text())


def _module_spec_paths(spec_dir: Path, module_name: str) -> Dict[str, Path]:
    suffix = f"_{module_name}.json"
    return {
        "L1": spec_dir / f"L1_functional{suffix}",
        "L2": spec_dir / f"L2_interface{suffix}",
        "L3": spec_dir / f"L3_verification{suffix}",
        "L5": spec_dir / f"L5_acceptance{suffix}",
    }


def _format_validation_issue(issue: ValidationIssue) -> str:
    if not issue.context:
        return f"[{issue.code}] {issue.message}"
    context_parts: List[str] = []
    for key in sorted(issue.context):
        value = issue.context[key]
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, sort_keys=True)
        else:
            rendered = str(value)
        context_parts.append(f"{key}={rendered}")
    context_text = ", ".join(context_parts)
    return f"[{issue.code}] {issue.message} ({context_text})"


def _raise_preplan_validation_errors(errors: List[ValidationIssue]) -> None:
    issue_lines = [f"- {_format_validation_issue(issue)}" for issue in errors]
    raise RuntimeError("Pre-plan validation failed:\n" + "\n".join(issue_lines))


def _spec_identity(planning_spec: PlanningSpec) -> dict[str, Any]:
    return {
        "spec_id": planning_spec.metadata.spec_id,
        "state": SpecificationState.FROZEN,
        "created_by": "spec_helper",
        "approved_by": "spec_helper",
    }


def _default_block_diagram(top_module: str) -> list[BlockDiagramNode]:
    return [
        BlockDiagramNode(
            node_id=top_module,
            description=f"Top module for {top_module}.",
            node_type="module",
            interface_refs=[],
            uses_standard_component=False,
            notes=None,
        )
    ]


def _clock_polarity(value: Any) -> ClockPolarity:
    text = str(value or "").strip().upper()
    return ClockPolarity.NEGEDGE if text in {"NEGEDGE", "NEG", "FALLING", "NEGATIVE"} else ClockPolarity.POSEDGE


def _reset_polarity(value: Any) -> ResetPolarity | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text in {"ACTIVE_LOW", "LOW", "0", "FALSE"}:
        return ResetPolarity.ACTIVE_LOW
    return ResetPolarity.ACTIVE_HIGH


def _signal_direction(value: Any) -> SignalDirection:
    text = str(value or "").strip().upper()
    if text in {"INPUT", "IN", "I"}:
        return SignalDirection.INPUT
    if text in {"OUTPUT", "OUT", "O"}:
        return SignalDirection.OUTPUT
    return SignalDirection.INOUT


def _artifact_list(raw_items: list[dict[str, Any]]) -> list[ArtifactRequirement]:
    items = [
        ArtifactRequirement(
            name=str(item.get("name") or "rtl"),
            description=str(item.get("description") or "Generated artifact"),
            mandatory=bool(item.get("mandatory", True)),
        )
        for item in raw_items
        if isinstance(item, dict)
    ]
    if items:
        return items
    return [
        ArtifactRequirement(name="rtl", description="Generated RTL source", mandatory=True),
        ArtifactRequirement(name="sim_log", description="Simulation log", mandatory=True),
    ]


def _acceptance_metric_list(raw_items: list[dict[str, Any]]) -> list[AcceptanceMetric]:
    items = [
        AcceptanceMetric(
            metric_id=str(item.get("metric_id") or "implementation_complete"),
            description=str(item.get("description") or "Implementation completes."),
            operator=str(item.get("operator") or "=="),
            target_value=str(item.get("target_value") or "1"),
            metric_source=(str(item.get("metric_source")).strip() or None) if item.get("metric_source") is not None else None,
        )
        for item in raw_items
        if isinstance(item, dict)
    ]
    if items:
        return items
    return [
        AcceptanceMetric(
            metric_id="implementation_complete",
            description="Implementation completes and produces RTL.",
            operator="==",
            target_value="1",
            metric_source="rtl",
        )
    ]


def _l1_from_module(planning_spec: PlanningSpec, module_name: str) -> L1Specification:
    module = planning_spec.modules[module_name]
    section = module.functional_intent
    return L1Specification(
        **_spec_identity(planning_spec),
        role_summary=section.role_summary or f"Implements module {module_name}.",
        key_rules=section.key_rules or ["Implement behavior exactly as described by the spec."],
        performance_intent=section.performance_intent or "Prompt-defined performance intent.",
        reset_semantics=section.reset_semantics or "Spec-defined safe reset behavior.",
        corner_cases=section.corner_cases or ["No additional corner cases documented."],
        open_questions=[],
    )


def _l2_from_module(planning_spec: PlanningSpec, module_name: str) -> L2Specification:
    module = planning_spec.modules[module_name]
    section = module.interface_contract
    clocking = [
        ClockingInfo(
            clock_name=str(item.get("clock_name") or "clk"),
            clock_polarity=_clock_polarity(item.get("clock_polarity")),
            reset_name=(str(item.get("reset_name")).strip() or None) if item.get("reset_name") is not None else None,
            reset_polarity=_reset_polarity(item.get("reset_polarity")),
            reset_is_async=item.get("reset_is_async"),
            description=(str(item.get("description")).strip() or None) if item.get("description") is not None else None,
        )
        for item in section.clocking
        if isinstance(item, dict)
    ]
    signals = [
        SignalDefinition(
            name=str(item.get("name") or ""),
            direction=_signal_direction(item.get("direction")),
            width_expr=str(item.get("width_expr") or "1"),
            semantics=(str(item.get("semantics")).strip() or None) if item.get("semantics") is not None else None,
        )
        for item in section.signals
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if not signals:
        signals = [
            SignalDefinition(name="in", direction=SignalDirection.INPUT, width_expr="1", semantics=None),
            SignalDefinition(name="out", direction=SignalDirection.OUTPUT, width_expr="1", semantics=None),
        ]
    handshake = [
        HandshakeProtocol(
            name=str(item.get("name") or "protocol"),
            rules=str(item.get("rules") or ""),
        )
        for item in section.handshake_semantics
        if isinstance(item, dict)
    ]
    params = [
        ConfigurationParameter(
            name=str(item.get("name") or ""),
            default_value=(str(item.get("default_value")).strip() or None) if item.get("default_value") is not None else None,
            description=(str(item.get("description")).strip() or None) if item.get("description") is not None else None,
        )
        for item in section.configuration_parameters
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    return L2Specification(
        **_spec_identity(planning_spec),
        clocking=clocking,
        signals=signals,
        handshake_semantics=handshake,
        transaction_unit=section.transaction_unit or "Spec-defined transaction/update unit.",
        configuration_parameters=params,
    )


def _l3_from_module(planning_spec: PlanningSpec, module_name: str) -> L3Specification:
    module = planning_spec.modules[module_name]
    section = module.verification_plan
    coverage_targets = [
        CoverageTarget(
            coverage_id=str(item.get("coverage_id") or f"{module_name}_coverage"),
            description=str(item.get("description") or "Coverage target"),
            metric_type=str(item.get("metric_type") or "event"),
            goal=float(item.get("goal")) if item.get("goal") not in (None, "") else None,
            notes=(str(item.get("notes")).strip() or None) if item.get("notes") is not None else None,
        )
        for item in section.coverage_targets
        if isinstance(item, dict)
    ]
    reset_constraints_raw = section.reset_constraints or {"min_cycles_after_reset": 0}
    scenarios = [
        VerificationScenario(
            scenario_id=str(item.get("scenario_id") or f"{module_name}_scenario"),
            description=str(item.get("description") or "Verification scenario"),
            stimulus=str(item.get("stimulus") or ""),
            oracle=str(item.get("oracle") or ""),
            pass_fail_criteria=str(item.get("pass_fail_criteria") or ""),
            illegal=bool(item.get("illegal", False)),
        )
        for item in section.scenarios
        if isinstance(item, dict)
    ]
    return L3Specification(
        **_spec_identity(planning_spec),
        test_goals=section.test_goals or [f"Implement and validate module {module_name}."],
        oracle_strategy=section.oracle_strategy or "Use the module specification as the oracle.",
        stimulus_strategy=section.stimulus_strategy or "Directed scenarios.",
        pass_fail_criteria=section.pass_fail_criteria or ["Module behavior matches the spec."],
        coverage_targets=coverage_targets,
        reset_constraints=ResetConstraint(
            min_cycles_after_reset=int(reset_constraints_raw.get("min_cycles_after_reset", 0)),
            ordering_notes=(str(reset_constraints_raw.get("ordering_notes")).strip() or None) if reset_constraints_raw.get("ordering_notes") is not None else None,
        ),
        scenarios=scenarios,
    )


def _l4_from_planning_spec(planning_spec: PlanningSpec) -> L4Specification:
    section = planning_spec.architecture_plan
    block_diagram = [
        BlockDiagramNode(
            node_id=str(item.get("node_id") or planning_spec.metadata.top_module),
            description=str(item.get("description") or f"Module {planning_spec.metadata.top_module}"),
            node_type=str(item.get("node_type") or "module"),
            interface_refs=list(item.get("interface_refs") or []),
            uses_standard_component=bool(item.get("uses_standard_component", False)),
            notes=(str(item.get("notes")).strip() or None) if item.get("notes") is not None else None,
        )
        for item in section.block_diagram
        if isinstance(item, dict)
    ] or _default_block_diagram(planning_spec.metadata.top_module)
    dependencies = [
        DependencyEdge(
            parent_id=str(item.get("parent_id") or ""),
            child_id=str(item.get("child_id") or ""),
            dependency_type=str(item.get("dependency_type") or "structural"),
        )
        for item in section.dependencies
        if isinstance(item, dict) and str(item.get("parent_id") or "").strip() and str(item.get("child_id") or "").strip()
    ]
    connections = []
    for item in section.connections:
        if not isinstance(item, dict):
            continue
        src = item.get("src") if isinstance(item.get("src"), dict) else {}
        dst = item.get("dst") if isinstance(item.get("dst"), dict) else {}
        if not src or not dst:
            continue
        connections.append(
            Connection(
                src=ConnectionEndpoint(
                    node_id=str(src.get("node_id") or ""),
                    port=str(src.get("port") or ""),
                    slice=(str(src.get("slice")).strip() or None) if src.get("slice") is not None else None,
                ),
                dst=ConnectionEndpoint(
                    node_id=str(dst.get("node_id") or ""),
                    port=str(dst.get("port") or ""),
                    slice=(str(dst.get("slice")).strip() or None) if dst.get("slice") is not None else None,
                ),
                width=(str(item.get("width")).strip() or None) if item.get("width") is not None else None,
                note=(str(item.get("note")).strip() or None) if item.get("note") is not None else None,
            )
        )
    clock_domains = [
        ClockDomain(
            name=str(item.get("name") or ""),
            frequency_hz=float(item.get("frequency_hz")) if item.get("frequency_hz") not in (None, "") else None,
            notes=(str(item.get("notes")).strip() or None) if item.get("notes") is not None else None,
        )
        for item in section.clock_domains
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    assertion_plan_raw = section.assertion_plan or {}
    return L4Specification(
        **_spec_identity(planning_spec),
        block_diagram=block_diagram,
        dependencies=dependencies,
        connections=connections,
        clock_domains=clock_domains,
        resource_strategy=section.resource_strategy or "Spec-defined implementation resources.",
        latency_budget=section.latency_budget or "Spec-defined latency budget.",
        assertion_plan=AssertionPlan(
            sva=[str(item) for item in assertion_plan_raw.get("sva", [])],
            scoreboard_assertions=[str(item) for item in assertion_plan_raw.get("scoreboard_assertions", [])],
        ),
    )


def _l5_from_module(planning_spec: PlanningSpec, module_name: str) -> L5Specification:
    module = planning_spec.modules[module_name]
    section = module.acceptance_contract
    return L5Specification(
        **_spec_identity(planning_spec),
        required_artifacts=_artifact_list(section.required_artifacts),
        acceptance_metrics=_acceptance_metric_list(section.acceptance_metrics),
        exclusions=section.exclusions,
        synthesis_target=section.synthesis_target,
    )


def _extract_module_nodes(l4: L4Specification, default_module: str) -> List[str]:
    if l4.block_diagram:
        nodes = [node.node_id for node in l4.block_diagram if not node.uses_standard_component]
        if not nodes:
            return [default_module]
        if default_module in nodes:
            return [default_module] + [node for node in nodes if node != default_module]
        return [default_module] + nodes
    return [default_module]


def _build_deps_map(
    module_nodes: List[str],
    l4: L4Specification,
) -> Dict[str, List[str]]:
    deps_map = {module: set() for module in module_nodes}
    module_set = set(module_nodes)
    all_nodes = {node.node_id for node in l4.block_diagram}
    for dep in l4.dependencies:
        parent = dep.parent_id
        child = dep.child_id
        if parent and child:
            unknown = [name for name in (parent, child) if name not in all_nodes]
            if unknown:
                raise RuntimeError(f"Unknown DAG dependency endpoint(s): {unknown}")
            # Interpret L4 edges as: child_id depends on parent_id.
            # Example: parent=submodule, child=top means top runs after submodule.
            if parent in module_set and child in module_set:
                deps_map.setdefault(child, set()).add(parent)
    return {child: sorted(parents) for child, parents in deps_map.items()}


def _collect_transitive_deps(node: str, deps_map: Dict[str, List[str]]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    visiting: set[str] = set()

    def _visit(curr: str) -> None:
        for dep in deps_map.get(curr, []):
            if dep in visiting:
                raise RuntimeError(f"DAG cycle detected involving {dep}")
            if dep in seen:
                continue
            visiting.add(dep)
            _visit(dep)
            visiting.remove(dep)
            seen.add(dep)
            ordered.append(dep)

    _visit(node)
    return ordered


def _filter_connections(connections, scope: set[str]) -> List[dict]:
    filtered = []
    for conn in connections:
        try:
            src_node = conn.src.node_id
            dst_node = conn.dst.node_id
        except Exception:
            continue
        if src_node in scope and dst_node in scope:
            filtered.append(conn.model_dump())
    return filtered


def _node_metadata_map(l4: L4Specification) -> Dict[str, Dict[str, str]]:
    meta: Dict[str, Dict[str, str]] = {}
    for node in l4.block_diagram:
        meta[node.node_id] = {
            "node_type": node.node_type or "",
            "description": node.description or "",
            "notes": node.notes or "",
        }
    return meta


def _infer_contract_style(*, module: str, top_module: str, node_type: str, description: str, notes: str) -> str:
    if module == top_module:
        return "integration"
    text = f"{node_type} {description} {notes}".lower()
    if any(token in text for token in ("comparator", "compare", "combinational", "mux", "decoder", "encoder")):
        return "combinational"
    if any(token in text for token in ("counter", "register", "sequential", "flop", "fifo", "ram", "fsm", "state")):
        return "sequential"
    return "unknown"


def _build_module_contract(
    *,
    module: str,
    top_module: str,
    node_meta: Dict[str, str],
    interface_signals: List[Dict[str, Any]],
    children: List[str],
) -> Dict[str, Any]:
    node_type = node_meta.get("node_type", "")
    description = node_meta.get("description", "")
    notes = node_meta.get("notes", "")
    style = _infer_contract_style(
        module=module,
        top_module=top_module,
        node_type=node_type,
        description=description,
        notes=notes,
    )
    contract: Dict[str, Any] = {
        "node_type": node_type or "module",
        "style": style,
        "description": description,
    }
    if style == "combinational":
        contract["forbid_edge_always"] = True
        contract["allow_internal_state"] = False
    if style in {"sequential", "integration"}:
        contract["allow_internal_state"] = True
    if style == "integration" and children:
        debug_outputs = [
            sig["name"]
            for sig in interface_signals
            if str(sig.get("direction", "")).upper() == "OUTPUT" and str(sig.get("name", "")).endswith("_dbg")
        ]
        if debug_outputs:
            contract["prefer_debug_passthrough"] = True
            contract["debug_outputs"] = debug_outputs
    return contract


def _module_port_index(l2_by_module: Dict[str, L2Specification]) -> Dict[str, set[str]]:
    index: Dict[str, set[str]] = {}
    for module, spec in l2_by_module.items():
        index[module] = {sig.name for sig in spec.signals if sig.name}
    return index


def _validate_l4_connection_endpoints(
    *,
    module_nodes: List[str],
    l4: L4Specification,
    port_index: Dict[str, set[str]],
) -> None:
    module_set = set(module_nodes)
    for conn in l4.connections:
        for side_name, endpoint in (("src", conn.src), ("dst", conn.dst)):
            node_id = endpoint.node_id
            if node_id not in module_set:
                continue
            port = endpoint.port
            declared = port_index.get(node_id, set())
            if port in declared:
                continue
            declared_list = ", ".join(sorted(declared))
            raise RuntimeError(
                f"L4.connections {side_name} endpoint '{node_id}.{port}' does not exist in "
                f"L2.signals for module '{node_id}'. Declared ports: [{declared_list}]"
            )


def _validate_child_connection_coverage(
    *,
    module_nodes: List[str],
    deps_map: Dict[str, List[str]],
    l4: L4Specification,
) -> None:
    modules_with_children = [module for module in module_nodes if deps_map.get(module)]
    if not modules_with_children:
        return

    if not l4.connections:
        parents = ", ".join(modules_with_children)
        raise RuntimeError(
            "L4.connections is empty, but these modules declare generated child dependencies: "
            f"{parents}. Add explicit L4.connections wiring for integration."
        )

    connected_nodes: set[str] = set()
    for conn in l4.connections:
        connected_nodes.add(conn.src.node_id)
        connected_nodes.add(conn.dst.node_id)

    for parent in modules_with_children:
        missing_children = [child for child in deps_map.get(parent, []) if child not in connected_nodes]
        if not missing_children:
            continue
        missing = ", ".join(missing_children)
        raise RuntimeError(
            f"Missing L4.connections coverage for child module(s) [{missing}] required by parent '{parent}'. "
            "Define explicit connection endpoints for each generated child module."
        )


def generate_from_specs(
    spec_dir: Path = SPEC_DIR,
    out_dir: Path = OUT_DIR,
    execution_policy: Dict[str, Any] | None = None,
) -> None:
    spec_dir = spec_dir.resolve()
    out_dir = out_dir.resolve()
    if _planning_spec_path(spec_dir).exists():
        planning_spec = _load_planning_spec(spec_dir)
        if not planning_spec.handoff.planner_ready or planning_spec.handoff.blocking_gaps:
            issues = planning_spec.handoff.blocking_gaps or []
            lines = [f"- {issue.field_path}: {issue.message}" for issue in issues] or ["- planner handoff blocked"]
            raise RuntimeError("Planning blocked by spec-helper rigor gaps:\n" + "\n".join(lines))

        lock = {
            "module_name": planning_spec.metadata.top_module,
            "top_module": planning_spec.metadata.top_module,
            "modules": planning_spec.metadata.module_inventory,
            "spec_id": str(planning_spec.metadata.spec_id),
        }
        top_module = planning_spec.metadata.top_module
        lock_modules = planning_spec.metadata.module_inventory

        l4 = _l4_from_planning_spec(planning_spec)
        l1_by_module: Dict[str, L1Specification] = {
            module_name: _l1_from_module(planning_spec, module_name)
            for module_name in planning_spec.metadata.module_inventory
        }
        l2_by_module: Dict[str, L2Specification] = {
            module_name: _l2_from_module(planning_spec, module_name)
            for module_name in planning_spec.metadata.module_inventory
        }
        l3_by_module: Dict[str, L3Specification] = {
            module_name: _l3_from_module(planning_spec, module_name)
            for module_name in planning_spec.metadata.module_inventory
        }
        l5_by_module: Dict[str, L5Specification] = {
            module_name: _l5_from_module(planning_spec, module_name)
            for module_name in planning_spec.metadata.module_inventory
        }
        l1 = l1_by_module[top_module]
        l2 = l2_by_module[top_module]
        l3 = l3_by_module[top_module]
        l5 = l5_by_module[top_module]
    else:
        lock_path = spec_dir / "lock.json"
        if not lock_path.exists():
            raise RuntimeError("Missing planning_spec.json. Run the spec helper before planning.")

        lock = _load_json(lock_path)
        top_module = str(lock.get("top_module") or lock.get("module_name") or "demo_module")
        lock_modules = lock.get("modules")

        l1 = L1Specification.model_validate_json((spec_dir / "L1_functional.json").read_text())
        l2 = L2Specification.model_validate_json((spec_dir / "L2_interface.json").read_text())
        l3 = L3Specification.model_validate_json((spec_dir / "L3_verification.json").read_text())
        l4 = L4Specification.model_validate_json((spec_dir / "L4_architecture.json").read_text())
        l5 = L5Specification.model_validate_json((spec_dir / "L5_acceptance.json").read_text())

        l1_by_module = {}
        l2_by_module = {}
        l3_by_module = {}
        l5_by_module = {}

        module_nodes = _extract_module_nodes(l4, top_module)
        for module in module_nodes:
            if module == top_module:
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

    execution_policy = execution_policy or {}
    verification_profile = str(execution_policy.get("verification_profile", "testbench-agent"))
    module_nodes = _extract_module_nodes(l4, top_module)
    node_meta_map = _node_metadata_map(l4)
    if lock_modules:
        missing = [node for node in module_nodes if node not in lock_modules]
        extra = [node for node in lock_modules if node not in module_nodes]
        if missing:
            raise RuntimeError(f"Lock missing required block-diagram modules: {missing}")
        if extra:
            raise RuntimeError(f"Lock contains modules not generated from block diagram: {extra}")
    if len(set(module_nodes)) != len(module_nodes):
        raise RuntimeError(f"Duplicate module ids in block diagram: {module_nodes}")

    deps_map = _build_deps_map(module_nodes, l4)

    top_specs = {"L1": l1, "L2": l2, "L3": l3, "L5": l5}
    child_specs = {
        module: {
            "L1": l1_by_module[module],
            "L2": l2_by_module[module],
            "L3": l3_by_module[module],
            "L5": l5_by_module[module],
        }
        for module in module_nodes
        if module != top_module
    }
    preplan_validation = validate_preplan_inputs(
        lock=lock,
        top_specs=top_specs,
        child_specs=child_specs,
        l4=l4,
        execution_policy=execution_policy,
    )
    if preplan_validation.errors:
        _raise_preplan_validation_errors(preplan_validation.errors)

    port_index = _module_port_index(l2_by_module)
    _validate_l4_connection_endpoints(module_nodes=module_nodes, l4=l4, port_index=port_index)
    _validate_child_connection_coverage(module_nodes=module_nodes, deps_map=deps_map, l4=l4)

    nodes: Dict[str, Dict[str, Any]] = {}
    for module in module_nodes:
        mod_l1 = l1_by_module[module]
        mod_l2 = l2_by_module[module]
        mod_l3 = l3_by_module[module]
        mod_l5 = l5_by_module[module]

        children = deps_map.get(module, [])
        dep_order = _collect_transitive_deps(module, deps_map)

        rtl_file = f"rtl/{module}.sv"
        tb_file = f"rtl/{module}_tb.sv"
        rtl_files = [f"rtl/{dep}.sv" for dep in dep_order] + [rtl_file]

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

        scope = {module} | set(dep_order)
        node_connections = _filter_connections(l4.connections, scope)
        node_contract = _build_module_contract(
            module=module,
            top_module=top_module,
            node_meta=node_meta_map.get(module, {}),
            interface_signals=interface_signals,
            children=children,
        )
        testbench_contract = build_testbench_contract(
            interface_signals=interface_signals,
            raw_clocking=clocking,
            module_contract=node_contract,
            reset_semantics=mod_l1.reset_semantics,
        )

        nodes[module] = {
            "rtl_file": rtl_file,
            "rtl_files": rtl_files,
            "testbench_file": tb_file,
            "interface": {"signals": interface_signals},
            "uses_library": [],
            "clocking": clocking,
            "coverage_goals": coverage_goals,
            "demo_behavior": demo_behavior,
            "verification": verification,
            "acceptance": acceptance,
            "verification_scope": verification_profile,
            "children": children,
            "connections": node_connections,
            "module_contract": node_contract,
            "testbench_contract": testbench_contract,
        }

    design_context = {
        "design_context_hash": None,
        "nodes": nodes,
        "standard_library": {},
        "top_module": top_module,
        "modules": module_nodes,
        "connections": [conn.model_dump() for conn in l4.connections],
        "execution_policy": execution_policy,
    }
    if preplan_validation.warnings:
        design_context["preplan_validation"] = {
            "profile": preplan_validation.profile,
            "warnings": [
                {
                    "code": warning.code,
                    "severity": warning.severity,
                    "message": warning.message,
                    "context": warning.context,
                }
                for warning in preplan_validation.warnings
            ],
        }
    design_context["design_context_hash"] = _hash_dict(design_context["nodes"])

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
