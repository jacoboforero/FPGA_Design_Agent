from pathlib import Path
import json

from core.schemas.contracts import EntityType, TaskMessage, TaskPriority, TaskStatus, WorkerType
from workers.distill.worker import DistillWorker


def _make_task(node_id: str, attempt: int = 1) -> TaskMessage:
    return TaskMessage(
        priority=TaskPriority.MEDIUM,
        entity_type=EntityType.LIGHT_DETERMINISTIC,
        task_type=WorkerType.DISTILLATION,
        context={"node_id": node_id, "attempt": attempt},
    )


def _write_minimal_vcd(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "$date",
                "$end",
                "$version",
                "$end",
                "$timescale 1ps $end",
                "$scope module tb $end",
                "$var wire 1 ! clk $end",
                "$upscope $end",
                "$enddefinitions $end",
                "#0",
                "0!",
                "#10",
                "1!",
                "#20",
                "0!",
            ]
        )
        + "\n"
    )


def test_distill_worker_falls_back_to_wave_vcd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    node_id = "TopModule"
    sim_dir = Path("artifacts/task_memory") / node_id / "sim_attempt1"
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "log.txt").write_text("FAIL cycle=5 time=20 clk=0\nMismatches: 3 in 41 samples\n")
    _write_minimal_vcd(sim_dir / "wave.vcd")

    worker = DistillWorker(connection_params=None, stop_event=None)
    result = worker.handle_task(_make_task(node_id=node_id, attempt=1))

    assert result.status is TaskStatus.SUCCESS
    payload = json.loads(Path(result.distilled_dataset.data_path).read_text())
    assert payload["waveform_path"].endswith("wave.vcd")
    assert payload["waveform_source"] == "wave_vcd"
    assert "waveform_source=wave_vcd" in result.log_output


def test_distill_worker_prefers_artifact_path_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    node_id = "TopModule"
    sim_dir = Path("artifacts/task_memory") / node_id / "sim_attempt1"
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "log.txt").write_text("FAIL cycle=7 time=30 clk=1\nMismatches: 5 in 41 samples\n")
    _write_minimal_vcd(sim_dir / "waveform.vcd")
    _write_minimal_vcd(sim_dir / "wave.vcd")
    custom_wave = Path("artifacts/custom/debug_wave.vcd")
    custom_wave.parent.mkdir(parents=True, exist_ok=True)
    _write_minimal_vcd(custom_wave)
    (sim_dir / "artifact_path.txt").write_text(str(custom_wave))

    worker = DistillWorker(connection_params=None, stop_event=None)
    result = worker.handle_task(_make_task(node_id=node_id, attempt=1))

    assert result.status is TaskStatus.SUCCESS
    payload = json.loads(Path(result.distilled_dataset.data_path).read_text())
    assert payload["waveform_path"] == str(custom_wave)
    assert payload["waveform_source"] == "artifact_path"
    assert "waveform_source=artifact_path" in result.log_output
