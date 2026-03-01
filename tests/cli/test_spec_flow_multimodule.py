from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.cli import spec_flow


def test_collect_specs_from_text_prefers_multimodule_flow_with_module_arg(tmp_path, monkeypatch):
    monkeypatch.setattr(spec_flow, "SPEC_DIR", tmp_path / "specs")
    monkeypatch.setattr(spec_flow, "_require_gateway", lambda: object())

    called: dict[str, object] = {}

    def _fake_collect_multi(gateway, spec_text, spec_path, interactive):
        called["gateway"] = gateway
        called["spec_text"] = spec_text
        called["spec_path"] = spec_path
        called["interactive"] = interactive
        return {"mode": "multi"}

    monkeypatch.setattr(spec_flow, "_collect_multi_specs", _fake_collect_multi)

    spec_text = (
        "Module: top\n"
        "L1\nRole summary: top\n\n"
        "Module: child\n"
        "L1\nRole summary: child\n"
    )
    result = spec_flow.collect_specs_from_text("ignored_name", spec_text, interactive=False)
    assert result == {"mode": "multi"}
    assert called["interactive"] is False


def test_collect_specs_from_text_benchmark_skips_gateway(monkeypatch, tmp_path):
    monkeypatch.setattr(spec_flow, "SPEC_DIR", tmp_path / "specs")
    monkeypatch.setattr(spec_flow, "_require_gateway", lambda: (_ for _ in ()).throw(AssertionError("unexpected")))
    monkeypatch.setattr(spec_flow, "_ensure_single_module_contract", lambda *args, **kwargs: None)
    monkeypatch.setattr(spec_flow, "_write_artifacts", lambda *args, **kwargs: "spec-id")
    monkeypatch.setattr(spec_flow, "_write_lock", lambda *args, **kwargs: None)

    seen: dict[str, object] = {}

    def _fake_invoke(gateway, spec_text, checklist, **kwargs):
        seen["gateway"] = gateway
        checklist["module_name"] = "demo"
        return checklist, spec_text

    monkeypatch.setattr(spec_flow, "_invoke_complete_checklist", _fake_invoke)

    result = spec_flow.collect_specs_from_text(
        "demo",
        "Module: demo\nL1\nRole summary: demo\n",
        interactive=False,
        spec_profile="benchmark",
    )
    assert seen["gateway"] is None
    assert result["module_name"] == "demo"


def test_validate_module_inventory_raises_when_l4_nodes_missing_module_sections():
    top_checklist = {
        "L4": {
            "block_diagram": [
                {"node_id": "top", "uses_standard_component": False},
                {"node_id": "child_a", "uses_standard_component": False},
                {"node_id": "child_b", "uses_standard_component": False},
            ]
        }
    }
    with pytest.raises(RuntimeError, match="missing Module section"):
        spec_flow._validate_module_inventory(
            module_names=["top", "child_a"],
            top_module="top",
            top_checklist=top_checklist,
        )


def test_canonical_modules_excludes_standard_components():
    top_checklist = {
        "L4": {
            "block_diagram": [
                {"node_id": "top", "uses_standard_component": False},
                {"node_id": "lib_fifo", "uses_standard_component": True},
                {"node_id": "core_a", "uses_standard_component": False},
            ]
        }
    }
    canonical = spec_flow._canonical_modules_from_top_checklist(top_checklist, "top")
    assert canonical == ["top", "core_a"]


def test_collect_multi_specs_raises_when_l4_declares_missing_module_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(spec_flow, "SPEC_DIR", tmp_path / "specs")

    captured_artifacts = []

    def _fake_write_artifacts(spec_text, checklist, spec_path, module_name, spec_id=None, filename_suffix=""):  # noqa: ARG001
        captured_artifacts.append(module_name)
        return spec_id

    top_checklist = {
        "module_name": "top",
        "L1": {
            "role_summary": "top role",
            "key_rules": ["top rule"],
            "performance_intent": "single-cycle",
            "reset_semantics": "active-low reset",
            "corner_cases": [],
            "open_questions": [],
        },
        "L2": {
            "clocking": [{"clock_name": "clk", "reset_name": "rst_n", "reset_polarity": "ACTIVE_LOW", "reset_is_async": True}],
            "signals": [{"name": "clk", "direction": "INPUT", "width_expr": "1"}, {"name": "rst_n", "direction": "INPUT", "width_expr": "1"}],
            "handshake_semantics": [],
            "transaction_unit": "one update",
            "configuration_parameters": [],
        },
        "L3": {
            "coverage_targets": [],
            "reset_constraints": {"min_cycles_after_reset": 0},
        },
        "L4": {
            "block_diagram": [
                {"node_id": "top", "description": "top block", "node_type": "top_level", "uses_standard_component": False},
                {"node_id": "child_a", "description": "child block", "node_type": "submodule", "uses_standard_component": False},
            ],
            "clock_domains": [],
            "resource_strategy": "minimal",
            "latency_budget": "1 cycle",
            "assertion_plan": {"sva": [], "scoreboard_assertions": []},
            "connections": [],
        },
        "L5": {
            "required_artifacts": [],
            "acceptance_metrics": [],
            "exclusions": [],
            "synthesis_target": "fpga_generic",
        },
    }

    def _fake_complete_checklist(gateway, spec_text, checklist, interactive, spec_path=None):
        return top_checklist, spec_text

    monkeypatch.setattr(spec_flow, "_write_artifacts", _fake_write_artifacts)
    monkeypatch.setattr(spec_flow, "_complete_checklist", _fake_complete_checklist)

    spec_text = "Module: top\nL1\nRole summary: top\n"
    spec_path = tmp_path / "spec_input.txt"
    spec_path.write_text(spec_text)

    with pytest.raises(RuntimeError, match="missing Module section\\(s\\): child_a"):
        spec_flow._collect_multi_specs(object(), spec_text, spec_path, interactive=False)

    # Only declared module artifacts should have been written before validation fails.
    assert captured_artifacts == ["top"]


def test_autogenerated_comparator_child_is_combinational():
    top_checklist = {
        "L1": {
            "performance_intent": "single cycle",
            "reset_semantics": "active-low reset",
        },
        "L2": {
            "clocking": [{"clock_name": "clk", "reset_name": "rst_n"}],
            "signals": [
                {"name": "clk", "direction": "INPUT", "width_expr": "1"},
                {"name": "rst_n", "direction": "INPUT", "width_expr": "1"},
                {"name": "count_dbg", "direction": "OUTPUT", "width_expr": "8"},
                {"name": "duty_dbg", "direction": "OUTPUT", "width_expr": "8"},
            ],
            "handshake_semantics": [],
            "transaction_unit": "n/a",
            "configuration_parameters": [],
        },
        "L3": {"coverage_targets": [], "reset_constraints": {"min_cycles_after_reset": 0}},
        "L4": {
            "block_diagram": [
                {"node_id": "top", "node_type": "top_level", "uses_standard_component": False},
                {"node_id": "pwm_compare8", "node_type": "comparator", "uses_standard_component": False},
            ],
            "clock_domains": [],
            "resource_strategy": "minimal",
            "latency_budget": "same-cycle",
            "assertion_plan": {"sva": [], "scoreboard_assertions": []},
            "connections": [],
        },
        "L5": {"required_artifacts": [], "acceptance_metrics": [], "exclusions": [], "synthesis_target": "fpga_generic"},
    }

    child = spec_flow._build_autogenerated_child_checklist(top_checklist, "pwm_compare8")
    signal_names = [sig["name"] for sig in child["L2"]["signals"]]
    assert isinstance(child["L2"]["clocking"], list)
    assert len(child["L2"]["clocking"]) == 1
    assert child["L2"]["clocking"][0]["clock_name"] == "clk"
    assert "clk" not in signal_names
    assert "rst_n" not in signal_names
    assert set(signal_names) >= {"count", "duty", "pwm_out"}


def test_collect_specs_from_text_direct_parse_single_module(tmp_path, monkeypatch):
    monkeypatch.setattr(spec_flow, "SPEC_DIR", tmp_path / "specs")
    monkeypatch.setattr(spec_flow, "_require_gateway", lambda: (_ for _ in ()).throw(AssertionError("unexpected")))
    spec_path = Path(__file__).resolve().parents[1] / "test_specs" / "01_counter3_basic.txt"
    payload = spec_path.read_text()

    result = spec_flow.collect_specs_from_text("counter3", payload, interactive=False, direct_parse=True)
    lock = json.loads((tmp_path / "specs" / "lock.json").read_text())

    assert result["module_name"] == "counter3"
    assert lock["top_module"] == "counter3"
    assert lock["modules"] == ["counter3"]
    assert (tmp_path / "specs" / "L1_functional.json").exists()
    assert (tmp_path / "specs" / "L5_acceptance.json").exists()


def test_collect_specs_from_text_direct_parse_multimodule_requires_explicit_module_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(spec_flow, "SPEC_DIR", tmp_path / "specs")
    monkeypatch.setattr(spec_flow, "_require_gateway", lambda: (_ for _ in ()).throw(AssertionError("unexpected")))
    spec_path = Path(__file__).resolve().parents[1] / "test_specs" / "05_pwm_led_multimodule.txt"
    payload = spec_path.read_text()

    with pytest.raises(RuntimeError, match="missing Module section\\(s\\): pwm_counter8, duty_reg8, pwm_compare8"):
        spec_flow.collect_specs_from_text("ignored", payload, interactive=False, direct_parse=True)
