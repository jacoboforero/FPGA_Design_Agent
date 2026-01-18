from pathlib import Path
import json

from orchestrator import planner


def write_specs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "L1_functional.json").write_text(
        json.dumps({"module_name": "foo", "behavior": "pass through", "performance": "none"})
    )
    (root / "L2_interface.json").write_text(
        json.dumps(
            {
                "module_name": "foo",
                "clock": {"name": "clk", "freq_hz": 50e6},
                "reset": {"name": "rst_n", "active_low": True},
                "signals": [
                    {"name": "clk", "direction": "INPUT", "width": 1},
                    {"name": "rst_n", "direction": "INPUT", "width": 1},
                    {"name": "in_data", "direction": "INPUT", "width": 8},
                    {"name": "out_data", "direction": "OUTPUT", "width": 8},
                ],
            }
        )
    )
    (root / "L3_verification.json").write_text(
        json.dumps({"coverage_goals": {"branch": 0.8, "toggle": 0.7}, "test_plan": ["happy", "reset"]})
    )
    (root / "L4_architecture.json").write_text(json.dumps({"architecture": "na", "notes": ""}))
    (root / "L5_acceptance.json").write_text(
        json.dumps({"acceptance": "tests pass", "coverage_thresholds": {"branch": 0.8, "toggle": 0.7}})
    )
    (root / "lock.json").write_text(json.dumps({"locked_at": "now", "module_name": "foo"}))


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

    dag_nodes = dag["nodes"]
    assert dag_nodes[0]["id"] == "foo"
    assert dag_nodes[0]["state"] == "PENDING"
