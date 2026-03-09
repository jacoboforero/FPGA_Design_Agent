from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from adapters.observability.jsonl import JsonlFileSink
from core.observability.execution_metrics import ExecutionMetricsRecorder


@dataclass
class _FakeEvent:
    runtime: str
    event_type: str
    payload: dict
    timestamp: datetime


def test_jsonl_sink_writes_run_scoped_and_legacy_files(tmp_path):
    sink = JsonlFileSink(run_name="cli_full_20260308-000000", run_id="run-123", base_dir=tmp_path)
    sink.send(
        _FakeEvent(
            runtime="unit",
            event_type="test_event",
            payload={"ok": True},
            timestamp=datetime.now(timezone.utc),
        )
    )

    run_scoped = tmp_path / "runs" / "cli_full_20260308-000000" / "run-123" / "observability" / "events.jsonl"
    legacy = tmp_path / "cli_full_20260308-000000_events.jsonl"
    assert run_scoped.exists()
    assert legacy.exists()
    assert "test_event" in run_scoped.read_text(encoding="utf-8")
    assert "test_event" in legacy.read_text(encoding="utf-8")


def test_execution_metrics_writes_run_scoped_and_legacy_files(tmp_path):
    recorder = ExecutionMetricsRecorder(run_id="run-xyz", run_name="matrix_case", out_dir=tmp_path)
    path = recorder.write(costs_log_path="artifacts/observability/runs/matrix_case/run-xyz/observability/costs.jsonl")

    expected_run_scoped = tmp_path / "runs" / "matrix_case" / "run-xyz" / "observability" / "execution_metrics.json"
    expected_legacy = tmp_path / "matrix_case_execution_metrics.json"
    assert path == expected_run_scoped
    assert expected_run_scoped.exists()
    assert expected_legacy.exists()
