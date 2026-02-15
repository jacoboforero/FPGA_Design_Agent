from pathlib import Path

from core.schemas.contracts import EntityType, TaskMessage, TaskPriority, TaskStatus, WorkerType
from workers.acceptance.worker import AcceptanceWorker


def make_task(node_id: str, attempt: int = 1) -> TaskMessage:
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.ACCEPTANCE,
        context={
            "node_id": node_id,
            "attempt": attempt,
            "acceptance": {
                "required_artifacts": [{"name": "coverage_report", "mandatory": True}],
                "acceptance_metrics": [
                    {
                        "metric_id": "branch",
                        "operator": ">=",
                        "target_value": "0.85",
                        "metric_source": "coverage_report",
                    },
                    {
                        "metric_id": "toggle",
                        "operator": ">=",
                        "target_value": "0.75",
                        "metric_source": "coverage_report",
                    },
                ],
            },
        },
    )


def test_acceptance_fails_coverage_when_sim_failed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    node_id = "pwm_counter8"
    sim_log = Path("artifacts/task_memory") / node_id / "sim_attempt1" / "log.txt"
    sim_log.parent.mkdir(parents=True, exist_ok=True)
    sim_log.write_text("failure at cycle=4 time=37000: count mismatch\n")

    worker = AcceptanceWorker(connection_params=None, stop_event=None)
    result = worker.handle_task(make_task(node_id=node_id, attempt=1))

    assert result.status is TaskStatus.FAILURE
    assert "Acceptance gating failed" in result.log_output
    assert "Missing required artifact 'coverage_report'" in result.log_output


def test_acceptance_defers_coverage_when_sim_passed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    node_id = "duty_reg8"
    sim_log = Path("artifacts/task_memory") / node_id / "sim_attempt1" / "log.txt"
    sim_log.parent.mkdir(parents=True, exist_ok=True)
    sim_log.write_text("PASS: All checks passed through cycle 20\n")

    worker = AcceptanceWorker(connection_params=None, stop_event=None)
    result = worker.handle_task(make_task(node_id=node_id, attempt=1))

    assert result.status is TaskStatus.SUCCESS
    assert "Acceptance warnings" in result.log_output
    assert "coverage gating deferred" in result.log_output
