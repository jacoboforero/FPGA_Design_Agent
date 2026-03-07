from __future__ import annotations

from agents.spec_helper.checklist import build_empty_checklist, list_missing_fields, set_field


def test_assertion_plan_empty_lists_are_treated_as_present():
    checklist = build_empty_checklist()
    set_field(
        checklist,
        "L4.assertion_plan",
        {"sva": [], "scoreboard_assertions": []},
    )
    missing_paths = {item.path for item in list_missing_fields(checklist)}
    assert "L4.assertion_plan" not in missing_paths
