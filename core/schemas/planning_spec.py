"""
Canonical semantic planning spec saved by the spec helper and consumed by the planner.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PlanningSpecSourceRefs(BaseModel):
    original_spec_path: str
    clarification_log_path: Optional[str] = None


class PlanningSpecMetadata(BaseModel):
    spec_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    design_kind: Literal["single_module", "multi_module"]
    top_module: str
    module_inventory: List[str]
    source_refs: PlanningSpecSourceRefs


class FunctionalIntentSection(BaseModel):
    role_summary: str = ""
    key_rules: List[str] = Field(default_factory=list)
    performance_intent: str = ""
    reset_semantics: str = ""
    corner_cases: List[str] = Field(default_factory=list)


class InterfaceContractSection(BaseModel):
    clocking: List[Dict[str, Any]] = Field(default_factory=list)
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    handshake_semantics: List[Dict[str, Any]] = Field(default_factory=list)
    transaction_unit: str = ""
    configuration_parameters: List[Dict[str, Any]] = Field(default_factory=list)


class VerificationPlanSection(BaseModel):
    test_goals: List[str] = Field(default_factory=list)
    oracle_strategy: str = ""
    stimulus_strategy: str = ""
    pass_fail_criteria: List[str] = Field(default_factory=list)
    coverage_targets: List[Dict[str, Any]] = Field(default_factory=list)
    reset_constraints: Optional[Dict[str, Any]] = None
    scenarios: List[Dict[str, Any]] = Field(default_factory=list)


class AcceptanceContractSection(BaseModel):
    required_artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    acceptance_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    synthesis_target: Optional[str] = None


class ModulePlanningSpec(BaseModel):
    functional_intent: FunctionalIntentSection = Field(default_factory=FunctionalIntentSection)
    interface_contract: InterfaceContractSection = Field(default_factory=InterfaceContractSection)
    verification_plan: VerificationPlanSection = Field(default_factory=VerificationPlanSection)
    acceptance_contract: AcceptanceContractSection = Field(default_factory=AcceptanceContractSection)


class ArchitecturePlanSection(BaseModel):
    block_diagram: List[Dict[str, Any]] = Field(default_factory=list)
    dependencies: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)
    clock_domains: List[Dict[str, Any]] = Field(default_factory=list)
    resource_strategy: str = ""
    latency_budget: str = ""
    assertion_plan: Dict[str, Any] = Field(default_factory=lambda: {"sva": [], "scoreboard_assertions": []})


class AssumptionItem(BaseModel):
    scope: str
    field_path: str
    statement: str
    source: str = "spec_helper"


class OpenQuestionItem(BaseModel):
    scope: str
    field_path: str
    question: str


class DeferredItem(BaseModel):
    scope: str
    field_path: str
    reason: str


class UncertaintySection(BaseModel):
    assumptions: List[AssumptionItem] = Field(default_factory=list)
    open_questions: List[OpenQuestionItem] = Field(default_factory=list)
    deferred_items: List[DeferredItem] = Field(default_factory=list)


class HandoffIssue(BaseModel):
    field_path: str
    message: str
    policy: Optional[str] = None


class HandoffSection(BaseModel):
    interaction: Literal["interactive", "non_interactive"]
    rigor_level: Literal["L0", "L1", "L2", "L3", "L4", "L5"]
    planner_ready: bool
    blocking_gaps: List[HandoffIssue] = Field(default_factory=list)
    warnings: List[HandoffIssue] = Field(default_factory=list)


class PlanningSpec(BaseModel):
    version: int = 1
    metadata: PlanningSpecMetadata
    modules: Dict[str, ModulePlanningSpec]
    architecture_plan: ArchitecturePlanSection = Field(default_factory=ArchitecturePlanSection)
    uncertainty: UncertaintySection = Field(default_factory=UncertaintySection)
    handoff: HandoffSection


__all__ = [
    "PlanningSpec",
    "PlanningSpecMetadata",
    "PlanningSpecSourceRefs",
    "ModulePlanningSpec",
    "ArchitecturePlanSection",
    "UncertaintySection",
    "HandoffSection",
]
