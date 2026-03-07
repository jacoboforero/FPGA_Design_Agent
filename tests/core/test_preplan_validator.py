from uuid import uuid4

import pytest

from core.schemas.specifications import (
    AcceptanceMetric,
    ArtifactRequirement,
    AssertionPlan,
    BlockDiagramNode,
    ClockingInfo,
    ConfigurationParameter,
    Connection,
    ConnectionEndpoint,
    CoverageTarget,
    HandshakeProtocol,
    L1Specification,
    L2Specification,
    L3Specification,
    L4Specification,
    L5Specification,
    ResetConstraint,
    SignalDefinition,
    SignalDirection,
    SpecificationState,
)
from orchestrator.preplan_validator import validate_preplan_inputs


def _make_l1(spec_id, state):
    return L1Specification(
        spec_id=spec_id,
        state=state,
        created_by="tester",
        approved_by="tester",
        role_summary="pass through module",
        key_rules=["out_data mirrors in_data"],
        performance_intent="single-cycle",
        reset_semantics="async reset clears outputs",
        corner_cases=["reset during activity"],
        open_questions=[],
    )


def _make_l2(spec_id, state, in_width: str = "8", out_width: str = "8"):
    return L2Specification(
        spec_id=spec_id,
        state=state,
        created_by="tester",
        approved_by="tester",
        clocking=[ClockingInfo(clock_name="clk", reset_name="rst_n", reset_is_async=True)],
        signals=[
            SignalDefinition(name="clk", direction=SignalDirection.INPUT, width_expr="1", semantics="clock"),
            SignalDefinition(name="rst_n", direction=SignalDirection.INPUT, width_expr="1", semantics="reset"),
            SignalDefinition(name="in_data", direction=SignalDirection.INPUT, width_expr=in_width, semantics="input"),
            SignalDefinition(name="out_data", direction=SignalDirection.OUTPUT, width_expr=out_width, semantics="output"),
        ],
        handshake_semantics=[HandshakeProtocol(name="none", rules="none")],
        transaction_unit="one transfer per cycle",
        configuration_parameters=[ConfigurationParameter(name="DATA_WIDTH", default_value="8", description="data width")],
    )


def _make_l3(spec_id, state):
    return L3Specification(
        spec_id=spec_id,
        state=state,
        created_by="tester",
        approved_by="tester",
        test_goals=["passes data", "reset clears"],
        oracle_strategy="cycle-accurate reference",
        stimulus_strategy="directed reset + data",
        pass_fail_criteria=["outputs match reference"],
        coverage_targets=[
            CoverageTarget(coverage_id="branch", description="branch coverage", metric_type="branch", goal=0.8),
        ],
        reset_constraints=ResetConstraint(min_cycles_after_reset=1, ordering_notes="none"),
        scenarios=[],
    )


def _make_l4(spec_id, state):
    return L4Specification(
        spec_id=spec_id,
        state=state,
        created_by="tester",
        approved_by="tester",
        block_diagram=[
            BlockDiagramNode(
                node_id="top",
                description="top module",
                node_type="top_level",
                interface_refs=["top_if"],
                uses_standard_component=False,
            )
        ],
        dependencies=[],
        connections=[
            Connection(
                src=ConnectionEndpoint(node_id="top", port="in_data"),
                dst=ConnectionEndpoint(node_id="top", port="out_data"),
            )
        ],
        clock_domains=[],
        resource_strategy="registers only",
        latency_budget="1 cycle",
        assertion_plan=AssertionPlan(sva=["out_data == in_data"], scoreboard_assertions=["match"]),
    )


def _make_l5(spec_id, state):
    return L5Specification(
        spec_id=spec_id,
        state=state,
        created_by="tester",
        approved_by="tester",
        required_artifacts=[ArtifactRequirement(name="rtl", description="rtl")],
        acceptance_metrics=[
            AcceptanceMetric(
                metric_id="branch",
                description="branch coverage",
                operator=">=",
                target_value="0.8",
                metric_source="coverage_report",
            )
        ],
        exclusions=[],
        synthesis_target="fpga_generic",
    )


def _build_valid_inputs():
    spec_id = uuid4()
    state = SpecificationState.FROZEN
    top_specs = {
        "L1": _make_l1(spec_id, state),
        "L2": _make_l2(spec_id, state),
        "L3": _make_l3(spec_id, state),
        "L5": _make_l5(spec_id, state),
    }
    child_specs = {}
    l4 = _make_l4(spec_id, state)
    lock = {"module_name": "top", "top_module": "top", "modules": ["top"], "spec_id": str(spec_id)}
    return lock, top_specs, child_specs, l4


def _set_signal_width(l2: L2Specification, signal_name: str, width_expr: str) -> None:
    for signal in l2.signals:
        if signal.name == signal_name:
            signal.width_expr = width_expr
            return
    raise AssertionError(f"Signal {signal_name} not found")


def test_preplan_validator_passes_on_frozen_consistent_specs():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert result.errors == []
    assert result.warnings == []


def test_preplan_validator_fails_when_any_doc_not_frozen():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    top_specs["L3"].state = SpecificationState.APPROVED
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert any(issue.code == "PLV101" for issue in result.errors)


def test_preplan_validator_fails_on_child_spec_id_mismatch():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    child_specs["child_mod"] = {
        "L1": _make_l1(uuid4(), SpecificationState.FROZEN),
        "L2": _make_l2(uuid4(), SpecificationState.FROZEN),
        "L3": _make_l3(uuid4(), SpecificationState.FROZEN),
        "L5": _make_l5(uuid4(), SpecificationState.FROZEN),
    }
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert any(issue.code == "PLV204" for issue in result.errors)


def test_preplan_validator_fails_on_lock_spec_id_mismatch():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    lock["spec_id"] = str(uuid4())
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert any(issue.code == "PLV204" for issue in result.errors)


def test_preplan_validator_fails_on_malformed_slice():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    l4.connections[0].src.slice = "[7:]"
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert any(issue.code == "PLV301" for issue in result.errors)


def test_preplan_validator_fails_on_out_of_range_slice():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    l4.connections[0].src.slice = "[8]"
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert any(issue.code == "PLV303" for issue in result.errors)


def test_preplan_validator_fails_on_numeric_width_mismatch():
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    _set_signal_width(top_specs["L2"], "out_data", "4")
    result = validate_preplan_inputs(lock, top_specs, child_specs, l4, execution_policy={})
    assert any(issue.code == "PLV304" for issue in result.errors)


@pytest.mark.parametrize(
    ("profile", "expect_error"),
    [
        ("oracle_compare", False),
        ("hybrid_scoreboard", False),
        ("strict_tb_acceptance", True),
    ],
)
def test_preplan_validator_symbolic_unresolved_is_profile_aware(profile: str, expect_error: bool):
    lock, top_specs, child_specs, l4 = _build_valid_inputs()
    _set_signal_width(top_specs["L2"], "in_data", "DATA_W")
    _set_signal_width(top_specs["L2"], "out_data", "PAYLOAD_W")

    result = validate_preplan_inputs(
        lock,
        top_specs,
        child_specs,
        l4,
        execution_policy={"verification_profile": profile},
    )
    if expect_error:
        assert any(issue.code == "PLV306" for issue in result.errors)
    else:
        assert not result.errors
        assert any(issue.code == "PLV306" for issue in result.warnings)
