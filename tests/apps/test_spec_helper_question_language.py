from agents.spec_helper.checklist import list_field_info
from agents.spec_helper import llm_helper


def test_generate_followup_question_uses_human_language_context(monkeypatch):
    captured = {}

    def _fake_run_llm(gateway, messages, stage):
        captured["stage"] = stage
        captured["system"] = messages[0].content
        captured["user"] = messages[1].content
        return '{"question": "What should the module do immediately after reset?"}'

    field = {item.path: item for item in list_field_info()}["L1.reset_semantics"]
    monkeypatch.setattr(llm_helper, "_run_llm", _fake_run_llm)

    question = llm_helper.generate_followup_question(
        object(),
        field,
        checklist={"module_name": "counter3"},
        spec_text="3-bit counter with enable input.",
        area_label="behavior",
        display_label="reset behavior",
        planning_goal="Ask only for the minimum concrete detail needed now so planning can continue.",
    )

    assert question == "What should the module do immediately after reset?"
    assert captured["stage"] == "question"
    assert "minimum concrete detail needed right now" in captured["system"]
    assert "reset behavior" in captured["user"]
    assert "Current area" not in captured["user"]
    assert "behavior" in captured["user"]
    assert "L1" not in captured["system"]
    assert "L1" not in captured["user"]
    assert "L2" not in captured["system"]
    assert "L2" not in captured["user"]
    assert "functional_intent" not in captured["system"]
    assert "functional_intent" not in captured["user"]

