from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.observability.execution_metrics import ExecutionMetricsRecorder


def test_execution_metrics_recorder_writes_summary(tmp_path):
    recorder = ExecutionMetricsRecorder(run_id="r1", run_name="unit_run", out_dir=tmp_path)
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(milliseconds=120)
    t2 = t1 + timedelta(milliseconds=350)
    recorder.record_published(
        task_id="task-1",
        node_id="top",
        stage_kind="lint",
        attempt=1,
        task_type="LinterWorker",
        published_ts=t0,
    )
    recorder.record_received(task_id="task-1", runtime="worker_lint", received_ts=t1)
    recorder.record_completed(task_id="task-1", completed_ts=t2, status="SUCCESS")
    recorder.record_reaction(task_id="task-1", orchestrator_reaction_ms=15.0)
    recorder.finalize_record("task-1")

    path = recorder.write(costs_log_path="artifacts/observability/costs.jsonl")
    data = path.read_text()
    assert "task-1" in data
    assert "\"task_count\": 1" in data
    assert "\"orchestrator_reaction_ms\"" in data

