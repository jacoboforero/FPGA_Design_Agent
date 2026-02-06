from __future__ import annotations

import json

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
