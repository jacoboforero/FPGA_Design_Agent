"""
Rigor-policy evaluation for the spec helper.

The current extraction workflow still uses the legacy checklist shape
internally, but planner handoff strictness is evaluated against the new
L0-L5 rigor ladder.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Literal

from agents.spec_helper.checklist import CHECKLIST_SCHEMA, FieldInfo, get_field, is_missing, list_field_info

RigorLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]
DesignKind = Literal["single_module", "multi_module"]

_FIELD_INFO_BY_PATH = {field.path: field for field in list_field_info()}
_WIDTH_SYMBOL_RE = re.compile(r"[A-Za-z_]")
_NO_RESET_PATTERNS = (
    "no reset",
    "without reset",
    "reset: none",
    "reset none",
    "none",
    "n/a",
)


@dataclass(frozen=True)
class RigorGap:
    checklist_path: str
    semantic_path: str
    policy: str
    severity: str
    message: str
    description: str


def _semantic_path(module_name: str | None, checklist_path: str) -> str:
    module_name = str(module_name or "").strip() or "<module>"
    mapping = {
        "L1.role_summary": f"modules.{module_name}.functional_intent.role_summary",
        "L1.key_rules": f"modules.{module_name}.functional_intent.key_rules",
        "L1.performance_intent": f"modules.{module_name}.functional_intent.performance_intent",
        "L1.reset_semantics": f"modules.{module_name}.functional_intent.reset_semantics",
        "L1.corner_cases": f"modules.{module_name}.functional_intent.corner_cases",
        "L2.clocking": f"modules.{module_name}.interface_contract.clocking",
        "L2.signals": f"modules.{module_name}.interface_contract.signals",
        "L2.handshake_semantics": f"modules.{module_name}.interface_contract.handshake_semantics",
        "L2.transaction_unit": f"modules.{module_name}.interface_contract.transaction_unit",
        "L2.configuration_parameters": f"modules.{module_name}.interface_contract.configuration_parameters",
        "L3.test_goals": f"modules.{module_name}.verification_plan.test_goals",
        "L3.oracle_strategy": f"modules.{module_name}.verification_plan.oracle_strategy",
        "L3.stimulus_strategy": f"modules.{module_name}.verification_plan.stimulus_strategy",
        "L3.pass_fail_criteria": f"modules.{module_name}.verification_plan.pass_fail_criteria",
        "L3.coverage_targets": f"modules.{module_name}.verification_plan.coverage_targets",
        "L3.reset_constraints": f"modules.{module_name}.verification_plan.reset_constraints",
        "L3.scenarios": f"modules.{module_name}.verification_plan.scenarios",
        "L4.block_diagram": "architecture_plan.block_diagram",
        "L4.dependencies": "architecture_plan.dependencies",
        "L4.connections": "architecture_plan.connections",
        "L4.clock_domains": "architecture_plan.clock_domains",
        "L4.resource_strategy": "architecture_plan.resource_strategy",
        "L4.latency_budget": "architecture_plan.latency_budget",
        "L4.assertion_plan": "architecture_plan.assertion_plan",
        "L5.required_artifacts": f"modules.{module_name}.acceptance_contract.required_artifacts",
        "L5.acceptance_metrics": f"modules.{module_name}.acceptance_contract.acceptance_metrics",
        "L5.exclusions": f"modules.{module_name}.acceptance_contract.exclusions",
        "L5.synthesis_target": f"modules.{module_name}.acceptance_contract.synthesis_target",
    }
    return mapping.get(checklist_path, checklist_path)


def _policy_map() -> Dict[str, Dict[RigorLevel, str]]:
    return {
        "L1.role_summary": {"L0": "R", "L1": "R", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L1.key_rules": {"L0": "A", "L1": "R", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L1.performance_intent": {"L0": "D", "L1": "W", "L2": "A", "L3": "R", "L4": "R", "L5": "R"},
        "L1.reset_semantics": {"L0": "A", "L1": "A", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L1.corner_cases": {"L0": "W", "L1": "A", "L2": "A", "L3": "R", "L4": "R", "L5": "R"},
        "L2.signals": {"L0": "R", "L1": "R", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L2.clocking": {"L0": "A:Seq", "L1": "A:Seq", "L2": "R:Seq", "L3": "R:Seq", "L4": "R:Seq", "L5": "R:Seq"},
        "L2.handshake_semantics": {"L0": "D", "L1": "A:Proto", "L2": "A:Proto", "L3": "R:Proto", "L4": "R:Proto", "L5": "R:Proto"},
        "L2.transaction_unit": {"L0": "W", "L1": "A", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L2.configuration_parameters": {"L0": "D", "L1": "A:Param", "L2": "A:Param", "L3": "R:Param", "L4": "R:Param", "L5": "R:Param"},
        "L3.test_goals": {"L0": "A", "L1": "A", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L3.oracle_strategy": {"L0": "D", "L1": "A", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L3.stimulus_strategy": {"L0": "D", "L1": "W", "L2": "A", "L3": "R", "L4": "R", "L5": "R"},
        "L3.pass_fail_criteria": {"L0": "A", "L1": "A", "L2": "R", "L3": "R", "L4": "R", "L5": "R"},
        "L3.coverage_targets": {"L0": "D", "L1": "D", "L2": "W", "L3": "A", "L4": "R", "L5": "R"},
        "L3.reset_constraints": {"L0": "D", "L1": "A:Seq", "L2": "R:Seq", "L3": "R:Seq", "L4": "R:Seq", "L5": "R:Seq"},
        "L3.scenarios": {"L0": "D", "L1": "D", "L2": "W", "L3": "A", "L4": "R", "L5": "R"},
        "L4.block_diagram": {"L0": "D", "L1": "D", "L2": "A:Top", "L3": "R:TopMulti", "L4": "R:Top", "L5": "R:Top"},
        "L4.dependencies": {"L0": "D", "L1": "D", "L2": "D", "L3": "R:TopMulti", "L4": "R:TopMulti", "L5": "R:TopMulti"},
        "L4.connections": {"L0": "D", "L1": "D", "L2": "D", "L3": "A:TopMulti", "L4": "R:TopMulti", "L5": "R:TopMulti"},
        "L4.clock_domains": {"L0": "D", "L1": "D", "L2": "W", "L3": "A:Top", "L4": "R:TopCDC", "L5": "R:TopCDC"},
        "L4.resource_strategy": {"L0": "D", "L1": "W", "L2": "A:Top", "L3": "A:Top", "L4": "R:Top", "L5": "R:Top"},
        "L4.latency_budget": {"L0": "D", "L1": "W", "L2": "A:Top", "L3": "A:Top", "L4": "R:Top", "L5": "R:Top"},
        "L4.assertion_plan": {"L0": "D", "L1": "D", "L2": "W", "L3": "A:Top", "L4": "R:Top", "L5": "R:Top"},
        "L5.required_artifacts": {"L0": "D", "L1": "W", "L2": "A", "L3": "A", "L4": "R", "L5": "R"},
        "L5.acceptance_metrics": {"L0": "D", "L1": "W", "L2": "A", "L3": "A", "L4": "R", "L5": "R"},
        "L5.exclusions": {"L0": "D", "L1": "D", "L2": "W", "L3": "W", "L4": "A", "L5": "R"},
        "L5.synthesis_target": {"L0": "D", "L1": "D", "L2": "D", "L3": "D", "L4": "A", "L5": "R"},
    }


RIGOR_POLICY = _policy_map()


def _field_policy(path: str, rigor_level: RigorLevel) -> str:
    return RIGOR_POLICY.get(path, {}).get(rigor_level, "D")


def _signals(checklist: Dict[str, Any]) -> list[dict[str, Any]]:
    raw = get_field(checklist, "L2.signals")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _looks_sequential(checklist: Dict[str, Any]) -> bool:
    clocking = get_field(checklist, "L2.clocking")
    if isinstance(clocking, list) and clocking:
        return True
    reset_semantics = str(get_field(checklist, "L1.reset_semantics") or "").lower()
    normalized_reset = " ".join(reset_semantics.split())
    explicitly_no_reset = any(pattern in normalized_reset for pattern in _NO_RESET_PATTERNS)
    if normalized_reset and not explicitly_no_reset and "reset" in normalized_reset:
        return True
    signal_names = {str(item.get("name", "")).strip().lower() for item in _signals(checklist)}
    return any(name in signal_names for name in {"clk", "clock", "rst", "rst_n", "reset"})


def _looks_protocol_based(checklist: Dict[str, Any]) -> bool:
    handshake = get_field(checklist, "L2.handshake_semantics")
    if isinstance(handshake, list) and handshake:
        return True
    signal_names = {str(item.get("name", "")).strip().lower() for item in _signals(checklist)}
    protocol_tokens = ("valid", "ready", "req", "ack")
    return any(any(token in name for token in protocol_tokens) for name in signal_names)


def _looks_parameterized(checklist: Dict[str, Any]) -> bool:
    params = get_field(checklist, "L2.configuration_parameters")
    if isinstance(params, list) and params:
        return True
    for sig in _signals(checklist):
        width_expr = str(sig.get("width_expr", "")).strip()
        if _WIDTH_SYMBOL_RE.search(width_expr):
            return True
    return False


def _has_multiple_clock_domains(checklist: Dict[str, Any]) -> bool:
    domains = get_field(checklist, "L4.clock_domains")
    return isinstance(domains, list) and len(domains) > 1


def _policy_applies(
    policy: str,
    *,
    checklist: Dict[str, Any],
    design_kind: DesignKind,
    is_top_module: bool,
) -> tuple[str, bool]:
    if ":" not in policy:
        return policy, True
    base, tag = policy.split(":", 1)
    if tag == "Seq":
        return base, _looks_sequential(checklist)
    if tag == "Proto":
        return base, _looks_protocol_based(checklist)
    if tag == "Param":
        return base, _looks_parameterized(checklist)
    if tag == "Top":
        return base, is_top_module
    if tag == "TopMulti":
        return base, is_top_module and design_kind == "multi_module"
    if tag == "TopCDC":
        return base, is_top_module and _has_multiple_clock_domains(checklist)
    return base, True


def list_rigor_gaps(
    checklist: Dict[str, Any],
    *,
    rigor_level: RigorLevel,
    design_kind: DesignKind,
    is_top_module: bool,
) -> tuple[list[RigorGap], list[RigorGap], list[RigorGap], list[RigorGap]]:
    module_name = str(checklist.get("module_name") or "").strip() or None
    blockers: list[RigorGap] = []
    assumptions: list[RigorGap] = []
    warnings: list[RigorGap] = []
    deferred: list[RigorGap] = []

    for field in _iter_policy_fields():
        policy = _field_policy(field.path, rigor_level)
        policy, applies = _policy_applies(policy, checklist=checklist, design_kind=design_kind, is_top_module=is_top_module)
        if not applies or policy == "D":
            continue
        field_schema = _schema_for_path(field.path)
        value = get_field(checklist, field.path)
        missing = is_missing(value, field_schema)
        if not missing:
            continue
        gap = RigorGap(
            checklist_path=field.path,
            semantic_path=_semantic_path(module_name, field.path),
            policy=policy,
            severity="blocker" if policy == "R" else "warning",
            message=f"{field.path} is missing for rigor {rigor_level}.",
            description=field.description,
        )
        if policy == "R":
            blockers.append(gap)
        elif policy == "A":
            assumptions.append(gap)
        elif policy == "W":
            warnings.append(gap)
        else:
            deferred.append(gap)

    if rigor_level == "L2" and design_kind == "multi_module" and is_top_module:
        blockers.append(
            RigorGap(
                checklist_path="metadata.design_kind",
                semantic_path="metadata.design_kind",
                policy="R",
                severity="blocker",
                message="Multi-module planning needs the child-module breakdown and relationships to be captured before handoff.",
                description="Capture the child modules, their dependencies, and their connections before planning continues.",
            )
        )

    return blockers, assumptions, warnings, deferred


def planner_ready_for_checklist(
    checklist: Dict[str, Any],
    *,
    rigor_level: RigorLevel,
    design_kind: DesignKind,
    is_top_module: bool,
) -> bool:
    blockers, _, _, _ = list_rigor_gaps(
        checklist,
        rigor_level=rigor_level,
        design_kind=design_kind,
        is_top_module=is_top_module,
    )
    return not blockers


def _iter_policy_fields() -> Iterable[FieldInfo]:
    for path in RIGOR_POLICY:
        yield _FIELD_INFO_BY_PATH[path]


def _schema_for_path(path: str) -> Dict[str, Any]:
    parts = path.split(".")
    cur: Dict[str, Any] = CHECKLIST_SCHEMA
    for part in parts:
        raw = cur.get(part)
        if not isinstance(raw, dict):
            raise KeyError(path)
        if "type" in raw:
            return raw
        cur = raw
    raise KeyError(path)
