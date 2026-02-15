from __future__ import annotations

import json
from types import SimpleNamespace

from apps.cli.execution_narrator import ExecutionNarrator


def test_deterministic_narrative_writes_public_log(tmp_path):
    task_memory_root = tmp_path / "artifacts" / "task_memory"
    lines: list[str] = []
    narrator = ExecutionNarrator(
        task_memory_root=task_memory_root,
        mode="deterministic",
        emit_line=lines.append,
    )

    narrator.handle_event("state_transition", {"node_id": "counter", "state": "SIMULATING"})
    narrator.handle_event(
        "stage_result",
        {
            "node_id": "counter",
            "stage_kind": "sim",
            "attempt": 1,
            "status": "FAILURE",
            "log_output": "FAIL cycle=17 time=17000 mismatch count expected=3 got=2",
            "reflections": json.dumps({"summary": "Potential edge-aligned stimulus race."}),
        },
    )

    assert any("counter | simulation | attempt 1 | needs work" in line for line in lines)
    assert all("Reasoning:" not in line for line in lines)
    assert all("Evidence:" not in line for line in lines)
    assert any("Next I will" in line for line in lines)

    public_log = task_memory_root / "counter" / "public" / "narrative.md"
    assert public_log.exists()
    content = public_log.read_text()
    assert "mismatch count expected=3 got=2" in content


def test_llm_mode_falls_back_cleanly_when_gateway_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("USE_LLM", raising=False)
    lines: list[str] = []
    narrator = ExecutionNarrator(
        task_memory_root=tmp_path / "artifacts" / "task_memory",
        mode="llm",
        emit_line=lines.append,
    )

    payload = {
        "node_id": "adder",
        "stage_kind": "lint",
        "attempt": 1,
        "status": "SUCCESS",
        "log_output": "Verilator lint passed",
    }
    narrator.handle_event("stage_result", payload)
    narrator.handle_event("stage_result", payload)

    warnings = [line for line in lines if line.startswith("[narrative]")]
    assert len(warnings) == 1
    assert "fallback" in warnings[0]
    assert any("adder | rtl checks | attempt 1 | pass" in line.lower() for line in lines)


def test_execution_note_non_top_module_skip_message(tmp_path):
    lines: list[str] = []
    narrator = ExecutionNarrator(
        task_memory_root=tmp_path / "artifacts" / "task_memory",
        mode="deterministic",
        emit_line=lines.append,
    )

    narrator.handle_event(
        "execution_note",
        {"node_id": "child_mod", "note": "non_top_module_skip"},
    )

    assert any("child_mod | verification skipped" in line for line in lines)
    assert any("skipped testbench and simulation for this non-top module" in line.lower() for line in lines)


def test_execution_note_retry_reason_is_specific(tmp_path):
    lines: list[str] = []
    narrator = ExecutionNarrator(
        task_memory_root=tmp_path / "artifacts" / "task_memory",
        mode="deterministic",
        emit_line=lines.append,
    )

    narrator.handle_event(
        "execution_note",
        {"node_id": "top", "reason": "sim"},
    )

    assert any("top | retries stopped" in line for line in lines)
    assert any("retry guardrail for sim" in line.lower() for line in lines)


def test_llm_narrative_falls_back_when_card_conflicts_with_status(tmp_path, monkeypatch):
    class FakeGateway:
        provider = "openai"

        async def generate(self, messages, config):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "headline": "Simulation completed",
                        "narrative": "Everything passed without issues.",
                        "evidence": "Simulation log shows FAILURE at cycle=4.",
                        "next_step": "I will continue.",
                    }
                )
            )

    monkeypatch.setattr(ExecutionNarrator, "_init_llm_gateway", staticmethod(lambda: FakeGateway()))
    lines: list[str] = []
    narrator = ExecutionNarrator(
        task_memory_root=tmp_path / "artifacts" / "task_memory",
        mode="llm",
        emit_line=lines.append,
    )

    narrator.handle_event(
        "stage_result",
        {
            "node_id": "counter",
            "stage_kind": "sim",
            "attempt": 1,
            "status": "SUCCESS",
            "log_output": "PASS: All checks passed",
        },
    )

    assert any("counter | simulation | attempt 1 | pass" in line for line in lines)
    assert any("Simulation completed cleanly" in line for line in lines)
    assert not any("Simulation log shows FAILURE at cycle=4." in line for line in lines)
