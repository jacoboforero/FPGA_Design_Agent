"""
Tests for specification (L1-L5) schemas.
"""
from uuid import uuid4

import pytest

from core.schemas import (
    SpecificationLevel,
    SpecificationState,
    L1Specification,
    L2Specification,
    ClockingInfo,
    ClockPolarity,
    ResetPolarity,
    SignalDefinition,
    SignalDirection,
    HandshakeProtocol,
    ConfigurationParameter,
    L3Specification,
    ResetConstraint,
    VerificationScenario,
    CoverageTarget,
    L4Specification,
    BlockDiagramNode,
    DependencyEdge,
    ClockDomain,
    AssertionPlan,
    L5Specification,
    ArtifactRequirement,
    AcceptanceMetric,
    FrozenSpecification,
)


def build_l1(spec_id):
    return L1Specification(
        spec_id=spec_id,
        state=SpecificationState.FROZEN,
        created_by="architect",
        approved_by="architect",
        role_summary="Implements a streaming FIFO between two domains.",
        key_rules=["Preserve ordering", "Never drop data"],
        performance_intent="At least 500 MHz write/read capability.",
        reset_semantics="Outputs held low until reset deasserted synchronously.",
        corner_cases=["Simultaneous write/read at depth limits"],
        open_questions=[],
    )


def build_l2(spec_id):
    return L2Specification(
        spec_id=spec_id,
        state=SpecificationState.FROZEN,
        created_by="architect",
        approved_by="architect",
        upstream_refs={"L1": build_l1(spec_id).document_id},
        clocking=[
            ClockingInfo(
                clock_name="clk_a",
                clock_polarity=ClockPolarity.POSEDGE,
                reset_name="rst_a_n",
                reset_polarity=ResetPolarity.ACTIVE_LOW,
                reset_is_async=True,
            ),
            ClockingInfo(
                clock_name="clk_b",
                clock_polarity=ClockPolarity.NEGEDGE,
                reset_name="rst_b",
                reset_polarity=ResetPolarity.ACTIVE_HIGH,
                reset_is_async=False,
            ),
        ],
        signals=[
            SignalDefinition(name="data_in", direction=SignalDirection.INPUT, width_expr="DATA_WIDTH", semantics="payload"),
            SignalDefinition(name="data_out", direction=SignalDirection.OUTPUT, width_expr="DATA_WIDTH", semantics="payload"),
        ],
        handshake_semantics=[HandshakeProtocol(name="ready_valid", rules="ready && valid === transfer; backpressure allowed")],
        transaction_unit="beat",
        configuration_parameters=[ConfigurationParameter(name="DATA_WIDTH", default_value="32")],
    )


def build_l3(spec_id):
    return L3Specification(
        spec_id=spec_id,
        state=SpecificationState.FROZEN,
        created_by="verifier",
        approved_by="architect",
        upstream_refs={"L2": build_l2(spec_id).document_id},
        test_goals=["Throughput stress", "Illegal overflow detection"],
        oracle_strategy="Scoreboard compares queued vectors to outputs.",
        stimulus_strategy="Directed bursts + constrained random gaps.",
        pass_fail_criteria=["Scoreboard empty by end-of-test"],
        coverage_targets=[CoverageTarget(coverage_id="cov_depth", description="Depth levels", metric_type="state", goal=0.95)],
        reset_constraints=ResetConstraint(min_cycles_after_reset=5, ordering_notes="Write after two cycles"),
        scenarios=[
            VerificationScenario(
                scenario_id="happy_path",
                description="Write/read alternating",
                stimulus="Drive valid every cycle",
                oracle="Scoreboard match",
                pass_fail_criteria="No mismatches",
                illegal=False,
            )
        ],
    )


def build_l4(spec_id):
    return L4Specification(
        spec_id=spec_id,
        state=SpecificationState.FROZEN,
        created_by="planner",
        approved_by="architect",
        upstream_refs={"L3": build_l3(spec_id).document_id},
        block_diagram=[
            BlockDiagramNode(
                node_id="fifo_core",
                description="Dual-clock FIFO",
                node_type="custom",
                interface_refs=["data_in", "data_out"],
            )
        ],
        dependencies=[DependencyEdge(parent_id="fifo_core", child_id="fifo_ctrl", dependency_type="structural")],
        clock_domains=[ClockDomain(name="clk_a"), ClockDomain(name="clk_b")],
        resource_strategy="Use 512-entry dual-port RAM.",
        latency_budget="1 cycle write + 1 cycle read latency budgeted to meet L3 throughput.",
        assertion_plan=AssertionPlan(
            sva=["assert property (@(posedge clk_a) disable iff (!rst_a_n) ready |-> ##1 valid);"],
            scoreboard_assertions=["Scoreboard depth never negative."],
        ),
    )


def build_l5(spec_id):
    return L5Specification(
        spec_id=spec_id,
        state=SpecificationState.FROZEN,
        created_by="planner",
        approved_by="architect",
        upstream_refs={"L4": build_l4(spec_id).document_id},
        required_artifacts=[ArtifactRequirement(name="rtl", description="Synthesizable RTL file")],
        acceptance_metrics=[
            AcceptanceMetric(
                metric_id="cov_depth",
                description="Depth coverage",
                operator=">=",
                target_value="0.95",
                metric_source="coverage_report",
            )
        ],
        exclusions=[],
        synthesis_target="FPGA|Vivado",
    )


class TestSpecificationModels:
    def test_l1_specification_levels_and_fields(self):
        spec_id = uuid4()
        l1 = build_l1(spec_id)
        assert l1.level == SpecificationLevel.L1
        assert l1.state == SpecificationState.FROZEN
        assert "Implements a streaming FIFO" in l1.role_summary
        assert not l1.open_questions

    def test_l2_supports_multiple_clock_domains(self):
        spec_id = uuid4()
        l2 = build_l2(spec_id)
        assert l2.level == SpecificationLevel.L2
        assert len(l2.clocking) == 2
        domains = {clk.clock_name for clk in l2.clocking}
        assert {"clk_a", "clk_b"} == domains
        assert l2.signals[0].direction == SignalDirection.INPUT

    def test_l3_l4_l5_round_trip(self):
        spec_id = uuid4()
        l3 = build_l3(spec_id)
        l4 = build_l4(spec_id)
        l5 = build_l5(spec_id)

        assert l3.level == SpecificationLevel.L3
        assert l4.block_diagram[0].node_id == "fifo_core"
        assert l5.acceptance_metrics[0].operator == ">="

    def test_frozen_specification_success(self):
        spec_id = uuid4()
        frozen = FrozenSpecification(
            spec_id=spec_id,
            l1=build_l1(spec_id),
            l2=build_l2(spec_id),
            l3=build_l3(spec_id),
            l4=build_l4(spec_id),
            l5=build_l5(spec_id),
            design_context_uri="/artifacts/task_memory/designs/fifo_design_context.json",
            frozen_by="architect",
        )

        assert frozen.spec_id == spec_id
        assert frozen.l2.clocking[0].reset_polarity == ResetPolarity.ACTIVE_LOW

    def test_frozen_specification_requires_matching_state(self):
        spec_id = uuid4()
        bad_l1 = L1Specification(
            spec_id=spec_id,
            state=SpecificationState.APPROVED,
            created_by="architect",
            role_summary="...",
            key_rules=["rule"],
            performance_intent="...",
            reset_semantics="...",
            corner_cases=["..."],
        )

        with pytest.raises(ValueError, match="must be in FROZEN state"):
            FrozenSpecification(
                spec_id=spec_id,
                l1=bad_l1,
                l2=build_l2(spec_id),
                l3=build_l3(spec_id),
                l4=build_l4(spec_id),
                l5=build_l5(spec_id),
                frozen_by="architect",
            )

    def test_frozen_specification_requires_matching_spec_id(self):
        spec_id = uuid4()
        other_spec_id = uuid4()

        with pytest.raises(ValueError, match="spec_id mismatch"):
            FrozenSpecification(
                spec_id=spec_id,
                l1=build_l1(other_spec_id),
                l2=build_l2(spec_id),
                l3=build_l3(spec_id),
                l4=build_l4(spec_id),
                l5=build_l5(spec_id),
                frozen_by="architect",
            )
