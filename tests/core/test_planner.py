from pathlib import Path
import json
from uuid import uuid4

from orchestrator import planner
from core.schemas.specifications import (
    AcceptanceMetric,
    ArtifactRequirement,
    AssertionPlan,
    BlockDiagramNode,
    ClockDomain,
    ClockingInfo,
    ConfigurationParameter,
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


def write_specs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    spec_id = uuid4()
    created_by = "tester"
    state = SpecificationState.FROZEN

    l1 = L1Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=created_by,
        role_summary="pass through module",
        key_rules=["out_data mirrors in_data"],
        performance_intent="single-cycle",
        reset_semantics="async reset clears outputs",
        corner_cases=["reset during activity"],
        open_questions=[],
    )
    l2 = L2Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=created_by,
        clocking=[
            ClockingInfo(
                clock_name="clk",
                reset_name="rst_n",
                reset_is_async=True,
                description="single domain",
            )
        ],
        signals=[
            SignalDefinition(name="clk", direction=SignalDirection.INPUT, width_expr="1", semantics="clock"),
            SignalDefinition(name="rst_n", direction=SignalDirection.INPUT, width_expr="1", semantics="reset"),
            SignalDefinition(name="in_data", direction=SignalDirection.INPUT, width_expr="8", semantics="input"),
            SignalDefinition(name="out_data", direction=SignalDirection.OUTPUT, width_expr="8", semantics="output"),
        ],
        handshake_semantics=[HandshakeProtocol(name="none", rules="none")],
        transaction_unit="one transfer per cycle",
        configuration_parameters=[
            ConfigurationParameter(name="DATA_WIDTH", default_value="8", description="data width")
        ],
    )
    l3 = L3Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=created_by,
        test_goals=["passes data", "reset clears"],
        oracle_strategy="cycle-accurate reference",
        stimulus_strategy="directed reset + data",
        pass_fail_criteria=["outputs match reference"],
        coverage_targets=[
            CoverageTarget(coverage_id="branch", description="branch coverage", metric_type="branch", goal=0.8),
            CoverageTarget(coverage_id="toggle", description="toggle coverage", metric_type="toggle", goal=0.7),
        ],
        reset_constraints=ResetConstraint(min_cycles_after_reset=1, ordering_notes="none"),
        scenarios=[],
    )
    l4 = L4Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=created_by,
        block_diagram=[
            BlockDiagramNode(
                node_id="foo",
                description="top module",
                node_type="module",
                interface_refs=["foo_if"],
            )
        ],
        dependencies=[],
        clock_domains=[ClockDomain(name="clk", frequency_hz=50e6, notes="single domain")],
        resource_strategy="registers only",
        latency_budget="1 cycle",
        assertion_plan=AssertionPlan(sva=["out_data == in_data"], scoreboard_assertions=["match"]),
    )
    l5 = L5Specification(
        spec_id=spec_id,
        state=state,
        created_by=created_by,
        approved_by=created_by,
        required_artifacts=[
            ArtifactRequirement(name="rtl", description="rtl"),
            ArtifactRequirement(name="testbench", description="tb"),
        ],
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

    (root / "L1_functional.json").write_text(json.dumps(l1.model_dump(mode="json"), indent=2))
    (root / "L2_interface.json").write_text(json.dumps(l2.model_dump(mode="json"), indent=2))
    (root / "L3_verification.json").write_text(json.dumps(l3.model_dump(mode="json"), indent=2))
    (root / "L4_architecture.json").write_text(json.dumps(l4.model_dump(mode="json"), indent=2))
    (root / "L5_acceptance.json").write_text(json.dumps(l5.model_dump(mode="json"), indent=2))
    (root / "lock.json").write_text(
        json.dumps(
            {
                "locked_at": "now",
                "module_name": "foo",
                "top_module": "foo",
                "modules": ["foo"],
                "spec_id": str(spec_id),
            }
        )
    )


def test_planner_generates_design_context_and_dag(tmp_path: Path, monkeypatch):
    spec_dir = tmp_path / "specs"
    out_dir = tmp_path / "out"
    write_specs(spec_dir)

    planner.generate_from_specs(spec_dir=spec_dir, out_dir=out_dir)

    design_context = json.loads((out_dir / "design_context.json").read_text())
    dag = json.loads((out_dir / "dag.json").read_text())

    assert "design_context_hash" in design_context
    node = design_context["nodes"]["foo"]
    assert node["rtl_file"] == "rtl/foo.sv"
    assert node["testbench_file"] == "rtl/foo_tb.sv"
    assert node["interface"]["signals"]
    assert node["module_contract"]["style"] == "integration"

    dag_nodes = dag["nodes"]
    assert dag_nodes[0]["id"] == "foo"
    assert dag_nodes[0]["state"] == "PENDING"


def test_planner_ignores_standard_components_in_module_inventory(tmp_path: Path):
    spec_dir = tmp_path / "specs"
    out_dir = tmp_path / "out"
    write_specs(spec_dir)

    l4_path = spec_dir / "L4_architecture.json"
    l4 = json.loads(l4_path.read_text())
    l4["block_diagram"].append(
        {
            "node_id": "std_fifo",
            "description": "library fifo",
            "node_type": "fifo",
            "interface_refs": ["std_fifo_if"],
            "uses_standard_component": True,
            "notes": "provided by library",
        }
    )
    l4["dependencies"].append(
        {
            "parent_id": "foo",
            "child_id": "std_fifo",
            "dependency_type": "structural",
        }
    )
    l4_path.write_text(json.dumps(l4, indent=2))

    planner.generate_from_specs(spec_dir=spec_dir, out_dir=out_dir)

    design_context = json.loads((out_dir / "design_context.json").read_text())
    dag = json.loads((out_dir / "dag.json").read_text())
    assert design_context["modules"] == ["foo"]
    assert [node["id"] for node in dag["nodes"]] == ["foo"]


def test_planner_dependency_direction_child_depends_on_parent(tmp_path: Path):
    spec_dir = tmp_path / "specs"
    out_dir = tmp_path / "out"
    write_specs(spec_dir)

    # Add a child module in architecture.
    l4_path = spec_dir / "L4_architecture.json"
    l4 = json.loads(l4_path.read_text())
    l4["block_diagram"] = [
        {
            "node_id": "foo",
            "description": "top module",
            "node_type": "module",
            "interface_refs": ["foo_if"],
            "uses_standard_component": False,
            "notes": None,
        },
        {
            "node_id": "child_mod",
            "description": "child module",
            "node_type": "module",
            "interface_refs": ["child_if"],
            "uses_standard_component": False,
            "notes": None,
        },
    ]
    l4["dependencies"] = [
        {
            "parent_id": "child_mod",
            "child_id": "foo",
            "dependency_type": "structural",
        }
    ]
    l4_path.write_text(json.dumps(l4, indent=2))

    # Provide child specs by reusing the top spec payloads.
    for base in ("L1_functional", "L2_interface", "L3_verification", "L5_acceptance"):
        src = spec_dir / f"{base}.json"
        dst = spec_dir / f"{base}_child_mod.json"
        dst.write_text(src.read_text())

    lock_path = spec_dir / "lock.json"
    lock = json.loads(lock_path.read_text())
    lock["modules"] = ["foo", "child_mod"]
    lock["top_module"] = "foo"
    lock_path.write_text(json.dumps(lock, indent=2))

    planner.generate_from_specs(spec_dir=spec_dir, out_dir=out_dir)

    design_context = json.loads((out_dir / "design_context.json").read_text())
    assert design_context["nodes"]["child_mod"]["module_contract"]["style"] in {"unknown", "sequential", "combinational"}

    dag = json.loads((out_dir / "dag.json").read_text())
    nodes = {n["id"]: n for n in dag["nodes"]}
    assert nodes["foo"]["deps"] == ["child_mod"]
    assert nodes["child_mod"]["deps"] == []


def test_planner_infers_combinational_contract_for_comparator(tmp_path: Path):
    spec_dir = tmp_path / "specs"
    out_dir = tmp_path / "out"
    write_specs(spec_dir)

    l4_path = spec_dir / "L4_architecture.json"
    l4 = json.loads(l4_path.read_text())
    l4["block_diagram"] = [
        {
            "node_id": "foo",
            "description": "top wrapper",
            "node_type": "top_level",
            "interface_refs": ["foo_if"],
            "uses_standard_component": False,
            "notes": None,
        },
        {
            "node_id": "cmp",
            "description": "comparator stage",
            "node_type": "comparator",
            "interface_refs": ["cmp_if"],
            "uses_standard_component": False,
            "notes": None,
        },
    ]
    l4["dependencies"] = [{"parent_id": "cmp", "child_id": "foo", "dependency_type": "structural"}]
    l4_path.write_text(json.dumps(l4, indent=2))

    for base in ("L1_functional", "L2_interface", "L3_verification", "L5_acceptance"):
        src = spec_dir / f"{base}.json"
        dst = spec_dir / f"{base}_cmp.json"
        dst.write_text(src.read_text())

    lock_path = spec_dir / "lock.json"
    lock = json.loads(lock_path.read_text())
    lock["modules"] = ["foo", "cmp"]
    lock["top_module"] = "foo"
    lock_path.write_text(json.dumps(lock, indent=2))

    planner.generate_from_specs(spec_dir=spec_dir, out_dir=out_dir)

    design_context = json.loads((out_dir / "design_context.json").read_text())
    cmp_contract = design_context["nodes"]["cmp"]["module_contract"]
    assert cmp_contract["style"] == "combinational"
    assert cmp_contract["forbid_edge_always"] is True
