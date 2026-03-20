from agents.spec_helper.rigor import list_rigor_gaps


def _base_combinational_checklist():
    return {
        "module_name": "and2_demo",
        "L1": {
            "role_summary": "1-bit combinational AND gate.",
            "key_rules": ["y = a & b"],
            "performance_intent": "same-cycle combinational response",
            "reset_semantics": "No reset; output depends only on current inputs.",
            "corner_cases": ["all four input combinations"],
        },
        "L2": {
            "clocking": [],
            "signals": [
                {"name": "a", "direction": "INPUT", "width_expr": "1", "semantics": "input"},
                {"name": "b", "direction": "INPUT", "width_expr": "1", "semantics": "input"},
                {"name": "y", "direction": "OUTPUT", "width_expr": "1", "semantics": "output"},
            ],
            "handshake_semantics": [],
            "transaction_unit": "one combinational evaluation",
            "configuration_parameters": [],
        },
        "L3": {
            "test_goals": ["truth table matches"],
            "oracle_strategy": "direct truth table",
            "stimulus_strategy": "drive all combinations",
            "pass_fail_criteria": ["no mismatches"],
            "coverage_targets": [],
            "reset_constraints": {},
            "scenarios": [],
        },
        "L4": {
            "block_diagram": [],
            "dependencies": [],
            "connections": [],
            "clock_domains": [],
            "resource_strategy": "single AND operator",
            "latency_budget": "same-cycle",
            "assertion_plan": {"sva": [], "scoreboard_assertions": []},
        },
        "L5": {
            "required_artifacts": [],
            "acceptance_metrics": [],
            "exclusions": [],
            "synthesis_target": "fpga_generic",
        },
    }


def test_combinational_no_reset_does_not_require_clocking_or_reset_constraints():
    checklist = _base_combinational_checklist()
    blockers, assumptions, warnings, deferred = list_rigor_gaps(
        checklist,
        rigor_level="L2",
        design_kind="single_module",
        is_top_module=True,
    )
    all_paths = {gap.checklist_path for gap in [*blockers, *assumptions, *warnings, *deferred]}
    assert "L2.clocking" not in all_paths
    assert "L3.reset_constraints" not in all_paths


def test_explicit_clock_and_reset_signal_still_marks_module_sequential():
    checklist = _base_combinational_checklist()
    checklist["L2"]["signals"] = [
        {"name": "clk", "direction": "INPUT", "width_expr": "1", "semantics": "clock"},
        {"name": "rst_n", "direction": "INPUT", "width_expr": "1", "semantics": "reset"},
        {"name": "a", "direction": "INPUT", "width_expr": "1", "semantics": "input"},
        {"name": "y", "direction": "OUTPUT", "width_expr": "1", "semantics": "output"},
    ]
    checklist["L1"]["reset_semantics"] = "Active-low async reset clears y to 0."
    blockers, _, _, _ = list_rigor_gaps(
        checklist,
        rigor_level="L2",
        design_kind="single_module",
        is_top_module=True,
    )
    blocker_paths = {gap.checklist_path for gap in blockers}
    assert "L2.clocking" in blocker_paths
