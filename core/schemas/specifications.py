"""
Specification schemas for the multi-agent hardware design system.

These models represent the Tier-1 persistent planning artifacts (L1-L5) and
their aggregation into a frozen design context. Each level is modeled as an
extension of SpecificationDocument, which captures immutable metadata shared
across the checklist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator, ConfigDict


class SpecificationLevel(str, Enum):
    """Checklist levels."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class SpecificationState(str, Enum):
    """Workflow state of an individual specification artifact."""

    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    FROZEN = "FROZEN"


class SpecificationDocument(BaseModel):
    """
    Base model for every specification layer. Stores metadata common to the
    planning artifacts so that versions can be audited independently.
    """

    document_id: UUID = Field(default_factory=uuid4, description="Unique ID for this document revision.")
    spec_id: UUID = Field(default_factory=uuid4, description="Project-level identifier shared across all levels.")
    level: SpecificationLevel = Field(..., description="Checklist level (L1-L5).")
    revision: int = Field(default=1, ge=1, description="Monotonic revision number for this document.")
    state: SpecificationState = Field(default=SpecificationState.DRAFT, description="Workflow state for this artifact.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when this revision was created."
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp when this revision was last updated."
    )
    created_by: str = Field(..., description="Human author or agent responsible for this revision.")
    approved_by: Optional[str] = Field(None, description="Approver recorded when the document reaches APPROVED/FROZEN.")
    content_hash: Optional[str] = Field(None, description="Hash of canonicalized payload for integrity checks.")
    upstream_refs: Dict[str, UUID] = Field(
        default_factory=dict,
        description="References to upstream documents (e.g., {'L1': uuid}). Used to detect stale dependencies.",
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# L1 Specification
# ---------------------------------------------------------------------------


class L1Specification(SpecificationDocument):
    """Functional intent definition (plain-language design goal)."""

    level: Literal[SpecificationLevel.L1] = SpecificationLevel.L1
    role_summary: str = Field(..., description="One paragraph summary of the hardware block's responsibility.")
    key_rules: List[str] = Field(..., min_length=1, description="List of ordering, losslessness, flag, or error rules.")
    performance_intent: str = Field(..., description="Qualitative throughput/latency expectations.")
    reset_semantics: str = Field(..., description="Definition of what 'safe after reset' means.")
    corner_cases: List[str] = Field(..., description="Corner or illegal scenarios that must be handled.")
    open_questions: List[str] = Field(
        default_factory=list, description="Outstanding questions for human follow-up before freezing."
    )


# ---------------------------------------------------------------------------
# L2 Specification
# ---------------------------------------------------------------------------


class ClockPolarity(str, Enum):
    POSEDGE = "POSEDGE"
    NEGEDGE = "NEGEDGE"


class ResetPolarity(str, Enum):
    ACTIVE_HIGH = "ACTIVE_HIGH"
    ACTIVE_LOW = "ACTIVE_LOW"


class ClockingInfo(BaseModel):
    clock_name: str
    clock_polarity: ClockPolarity = ClockPolarity.POSEDGE
    reset_name: Optional[str] = Field(None, description="Associated reset signal name, if any.")
    reset_polarity: Optional[ResetPolarity] = Field(
        None, description="Polarity of the associated reset (ACTIVE_HIGH/ACTIVE_LOW)."
    )
    reset_is_async: Optional[bool] = Field(
        None, description="True if the reset is asynchronous to this clock domain."
    )
    description: Optional[str] = Field(
        None, description="Notes about the domain (e.g., derived clocks, gating, CDC strategy)."
    )


class SignalDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INOUT = "INOUT"


class SignalDefinition(BaseModel):
    name: str = Field(..., description="Signal identifier.")
    direction: SignalDirection = Field(..., description="Port direction (input/output/inout).")
    width_expr: str = Field(..., description="Bit width expression or parameter reference.")
    semantics: Optional[str] = Field(None, description="Protocol semantics (e.g., part of ready/valid).")


class HandshakeProtocol(BaseModel):
    name: str
    rules: str = Field(..., description="Human-readable description of the handshake/backpressure rules.")


class ConfigurationParameter(BaseModel):
    name: str
    default_value: Optional[str] = Field(None, description="Default value used when unspecified.")
    description: Optional[str] = None


class L2Specification(SpecificationDocument):
    """Interface contract."""

    level: Literal[SpecificationLevel.L2] = SpecificationLevel.L2
    clocking: List[ClockingInfo] = Field(
        ..., min_length=1, description="One or more clock/reset domains applicable to this module."
    )
    signals: List[SignalDefinition] = Field(..., min_length=1)
    handshake_semantics: List[HandshakeProtocol] = Field(default_factory=list)
    transaction_unit: str = Field(..., description="Beat/packet/word and ordering guarantees.")
    configuration_parameters: List[ConfigurationParameter] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# L3 Specification
# ---------------------------------------------------------------------------


class VerificationScenario(BaseModel):
    scenario_id: str
    description: str
    stimulus: str = Field(..., description="Stimulus or stimulus generation strategy.")
    oracle: str = Field(..., description="How correctness is determined for this scenario.")
    pass_fail_criteria: str = Field(..., description="Observable condition for success.")
    illegal: bool = Field(False, description="True if scenario covers illegal behavior.")


class CoverageTarget(BaseModel):
    coverage_id: str
    description: str
    metric_type: str = Field(..., description="Coverage domain (state, transition, event, etc.).")
    goal: Optional[float] = Field(None, description="Target ratio (0-1) or numeric threshold.")
    notes: Optional[str] = None


class ResetConstraint(BaseModel):
    min_cycles_after_reset: int = Field(..., ge=0)
    ordering_notes: Optional[str] = Field(None, description="Additional sequencing requirements.")


class L3Specification(SpecificationDocument):
    """Verification plan."""

    level: Literal[SpecificationLevel.L3] = SpecificationLevel.L3
    test_goals: List[str] = Field(..., min_length=1, description="Happy-path, boundary, and illegal goals.")
    oracle_strategy: str = Field(..., description="Scoreboard rules or reference models.")
    stimulus_strategy: str = Field(..., description="Directed scenarios plus randomization ranges.")
    pass_fail_criteria: List[str] = Field(..., description="Global pass/fail rules.")
    coverage_targets: List[CoverageTarget] = Field(default_factory=list)
    reset_constraints: ResetConstraint
    scenarios: List[VerificationScenario] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# L4 Specification
# ---------------------------------------------------------------------------


class BlockDiagramNode(BaseModel):
    node_id: str
    description: str
    node_type: str = Field(..., description="Functional classification or standard component name.")
    interface_refs: List[str] = Field(default_factory=list, description="IDs of interface definitions from L2.")
    uses_standard_component: bool = Field(False, description="True if node references a library component.")
    notes: Optional[str] = None


class DependencyEdge(BaseModel):
    parent_id: str
    child_id: str
    dependency_type: str = Field(..., description="e.g., structural, timing, configuration.")


class ClockDomain(BaseModel):
    name: str
    frequency_hz: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class AssertionPlan(BaseModel):
    sva: List[str] = Field(default_factory=list, description="Invariants enforced via SVA.")
    scoreboard_assertions: List[str] = Field(default_factory=list, description="Checks enforced in scoreboards.")


class L4Specification(SpecificationDocument):
    """Architecture / microarchitecture."""

    level: Literal[SpecificationLevel.L4] = SpecificationLevel.L4
    block_diagram: List[BlockDiagramNode] = Field(..., min_length=1)
    dependencies: List[DependencyEdge] = Field(default_factory=list)
    clock_domains: List[ClockDomain] = Field(default_factory=list)
    resource_strategy: str = Field(..., description="Resource allocations (FIFO/RAM sizes, etc.).")
    latency_budget: str = Field(..., description="Latency/throughput plan tied back to L3.")
    assertion_plan: AssertionPlan


# ---------------------------------------------------------------------------
# L5 Specification
# ---------------------------------------------------------------------------


class ArtifactRequirement(BaseModel):
    name: str
    description: str
    mandatory: bool = True


class AcceptanceMetric(BaseModel):
    metric_id: str = Field(..., description="Stable identifier, often matching coverage IDs.")
    description: str
    operator: str = Field(..., pattern=r"^(==|!=|>=|<=|>|<)$")
    target_value: str = Field(..., description="Value compared using operator (stored as string for flexibility).")
    metric_source: Optional[str] = Field(
        None, description="Where the metric originates (simulation log, coverage report, etc.)."
    )


class L5Specification(SpecificationDocument):
    """Acceptance and sign-off plan."""

    level: Literal[SpecificationLevel.L5] = SpecificationLevel.L5
    required_artifacts: List[ArtifactRequirement] = Field(..., min_length=1)
    acceptance_metrics: List[AcceptanceMetric] = Field(..., min_length=1)
    exclusions: List[str] = Field(default_factory=list, description="Explicitly documented limitations.")
    synthesis_target: Optional[str] = Field(None, description="Target technology/tool (FPGA, ASIC, etc.).")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class FrozenSpecification(BaseModel):
    """
    Immutable bundle that ties the approved versions of each level together and
    references the generated Design Context artifact.
    """

    spec_id: UUID
    l1: L1Specification
    l2: L2Specification
    l3: L3Specification
    l4: L4Specification
    l5: L5Specification
    design_context_uri: Optional[str] = Field(
        None, description="Path or URI to the frozen Design Context/DAG artifact."
    )
    frozen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    frozen_by: str = Field(..., description="Human approver who finalized the bundle.")

    @model_validator(mode="after")
    def ensure_consistency(self) -> "FrozenSpecification":
        for attr in ("l1", "l2", "l3", "l4", "l5"):
            doc = getattr(self, attr)
            if doc.state != SpecificationState.FROZEN:
                raise ValueError(f"{attr} must be in FROZEN state, got {doc.state}.")
            if doc.spec_id != self.spec_id:
                raise ValueError(f"{attr} spec_id mismatch: expected {self.spec_id}, got {doc.spec_id}.")
        return self


__all__ = [
    "SpecificationLevel",
    "SpecificationState",
    "SpecificationDocument",
    "L1Specification",
    "ClockPolarity",
    "ClockingInfo",
    "SignalDirection",
    "SignalDefinition",
    "HandshakeProtocol",
    "ConfigurationParameter",
    "L2Specification",
    "VerificationScenario",
    "CoverageTarget",
    "ResetConstraint",
    "L3Specification",
    "BlockDiagramNode",
    "DependencyEdge",
    "ClockDomain",
    "AssertionPlan",
    "L4Specification",
    "ArtifactRequirement",
    "AcceptanceMetric",
    "L5Specification",
    "FrozenSpecification",
]
