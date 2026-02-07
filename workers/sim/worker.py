"""
Simulation worker. Runs iverilog/vvp and fails hard if tools are missing.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
import pika
from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_retry_count, next_retry_headers, MAX_RETRIES

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class SimulationWorker(threading.Thread):
    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event

    def run(self) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.basic_qos(prefetch_count=1)
            for method, props, body in ch.consume("simulation_tasks", inactivity_timeout=0.5):
                if self.stop_event.is_set():
                    break
                if body is None:
                    continue
                try:
                    task = TaskMessage.model_validate_json(body)
                except Exception:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                try:
                    result = self.handle_task(task)
                except TaskInputError:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except RetryableError:
                    retry_count = get_retry_count(props)
                    if retry_count < MAX_RETRIES:
                        headers = next_retry_headers(props)
                        ch.basic_publish(
                            exchange=TASK_EXCHANGE,
                            routing_key=task.entity_type.value,
                            body=body,
                            properties=pika.BasicProperties(content_type="application/json", headers=headers),
                        )
                        ch.basic_ack(method.delivery_tag)
                    else:
                        ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except Exception as exc:  # noqa: BLE001
                    result = ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=f"Unhandled simulation error: {exc}",
                    )
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        iverilog = os.getenv("IVERILOG_PATH") or shutil.which("iverilog")
        vvp = os.getenv("VVP_PATH") or shutil.which("vvp")
        rtl_path = task.context.get("rtl_path")
        tb_path = task.context.get("tb_path")
        node_id = task.context.get("node_id")
        attempt = _parse_attempt(task.context.get("attempt"))
        if not iverilog or not vvp:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="Simulation tools missing; set IVERILOG_PATH and VVP_PATH or install iverilog/vvp.",
            )
        if not rtl_path:
            raise TaskInputError("Missing rtl_path in task context.")
        rtl_paths = task.context.get("rtl_paths") or [rtl_path]
        if not isinstance(rtl_paths, list):
            rtl_paths = [rtl_path]
        rtl_paths = [str(path) for path in rtl_paths if path]
        if not rtl_paths:
            raise TaskInputError("Missing rtl_paths in task context.")
        missing_rtl = [path for path in rtl_paths if not Path(path).exists()]
        if missing_rtl:
            raise TaskInputError(f"RTL missing: {missing_rtl}")
        try:
            sources = list(dict.fromkeys(rtl_paths))
            if tb_path:
                sources.append(tb_path)
            cmd = [iverilog, "-g2012", "-g2005-sv", "-o", "/tmp/sim.out", *sources]
            log_lines = []
            log_lines.append("[build]")
            log_lines.append(f"cmd: {' '.join(cmd)}")
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if build.returncode != 0:
                output = "\n".join(part for part in [build.stdout, build.stderr] if part).strip()
                if output:
                    log_lines.append(output)
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=None,
                    log_output="\n".join(log_lines),
                )
            run_cmd = [vvp, "/tmp/sim.out"]
            run = subprocess.run(run_cmd, capture_output=True, text=True, timeout=30)
            run_output = "\n".join(part for part in [run.stdout, run.stderr] if part).strip()
            has_failure_marker = _has_failure_marker(run_output)
            if run.returncode != 0 or has_failure_marker:
                log_lines.append("[run]")
                log_lines.append(f"cmd: {' '.join(run_cmd)}")
                if run_output:
                    log_lines.append(run_output)
                cycle, time_val = _extract_failure_info(run_output)
                log_lines.append("[analysis]")
                if run.returncode != 0:
                    log_lines.append(f"Simulation failed (exit code {run.returncode}).")
                else:
                    log_lines.append("Simulation reported failure in output; treating as failure.")
                if cycle is not None or time_val is not None:
                    cycle_msg = str(cycle) if cycle is not None else "unknown"
                    time_msg = str(time_val) if time_val is not None else "unknown"
                    log_lines.append(f"Detected failure cycle={cycle_msg} time={time_msg}.")
                else:
                    log_lines.append("No failure cycle/time found in log output.")

                artifacts_path = None
                rerun_log = _maybe_rerun_with_dump(
                    vvp=vvp,
                    node_id=node_id,
                    attempt=attempt,
                    cycle=cycle,
                    log_lines=log_lines,
                )
                if rerun_log.get("waveform_path"):
                    artifacts_path = rerun_log["waveform_path"]

                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=artifacts_path,
                    log_output="\n".join(log_lines),
                )
            emit_runtime_event(
                runtime="worker_sim",
                event_type="task_completed",
                payload={"task_id": str(task.task_id)},
            )
            log_lines.append("[run]")
            log_lines.append(f"cmd: {' '.join(run_cmd)}")
            if run_output:
                log_lines.append(run_output)
            else:
                log_lines.append("Simulation passed.")
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.SUCCESS,
                artifacts_path=None,
                log_output="\n".join(log_lines),
            )
        except subprocess.TimeoutExpired as exc:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Simulation timeout: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Simulation failed: {exc}",
            )

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


_FAIL_CYCLE_RE = re.compile(r"\bcycle\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_TIME_RE = re.compile(r"\btime\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_MARKER_RE = re.compile(r"\b(FAIL|ERROR)\b", re.IGNORECASE)


def _extract_failure_info(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    lines = text.splitlines()
    candidates = [line for line in lines if "FAIL" in line or "ERROR" in line]
    if not candidates:
        candidates = lines
    cycle = None
    time_val = None
    for line in candidates:
        if cycle is None:
            match = _FAIL_CYCLE_RE.search(line)
            if match:
                cycle = int(match.group(1))
        if time_val is None:
            match = _FAIL_TIME_RE.search(line)
            if match:
                time_val = int(match.group(1))
        if cycle is not None or time_val is not None:
            break
    return cycle, time_val


def _has_failure_marker(text: str | None) -> bool:
    if not text:
        return False
    return _FAIL_MARKER_RE.search(text) is not None


def _maybe_rerun_with_dump(
    *,
    vvp: str,
    node_id: str | None,
    attempt: int | None,
    cycle: int | None,
    log_lines: list[str],
) -> dict:
    if not node_id:
        log_lines.append("[rerun]")
        log_lines.append("Skipping waveform rerun (missing node_id in context).")
        return {}
    if cycle is None:
        log_lines.append("[rerun]")
        log_lines.append("Skipping waveform rerun (failure cycle not found; enable cycle logging in testbench).")
        return {}

    before = int(os.getenv("SIM_FAIL_WINDOW_BEFORE", "20"))
    after = int(os.getenv("SIM_FAIL_WINDOW_AFTER", "5"))
    start_cycle = max(0, cycle - before)
    end_cycle = cycle + after
    waveform_path = Path("artifacts/task_memory") / node_id / _stage_dir("sim", attempt) / "waveform.vcd"
    waveform_path.parent.mkdir(parents=True, exist_ok=True)

    # Many benches gate dumping with $dumpoff/$dumpon and (incorrectly) treat DUMP_START=0 as "disabled".
    # If we want to start at cycle 0, omit DUMP_START/DUMP_END entirely so the bench dumps from time 0.
    use_window = start_cycle > 0
    rerun_cmd = [vvp, "/tmp/sim.out", "+DUMP", f"+DUMP_FILE={waveform_path}"]
    if use_window:
        rerun_cmd.extend([f"+DUMP_START={start_cycle}", f"+DUMP_END={end_cycle}"])
    log_lines.append("[rerun]")
    if use_window:
        log_lines.append(f"Re-running for waveform capture (cycles {start_cycle}..{end_cycle}).")
    else:
        log_lines.append("Re-running for waveform capture from cycle 0 (window omitted; DUMP_START=0 can break some benches).")
    log_lines.append(f"cmd: {' '.join(rerun_cmd)}")
    try:
        rerun = subprocess.run(rerun_cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        log_lines.append(f"Waveform rerun failed: {exc}")
        return {}
    rerun_output = "\n".join(part for part in [rerun.stdout, rerun.stderr] if part).strip()
    if rerun_output:
        log_lines.append(rerun_output)
    if waveform_path.exists():
        log_lines.append(f"Waveform written to {waveform_path}.")
        return {"waveform_path": str(waveform_path)}
    log_lines.append("Waveform not generated; testbench may not support dump plusargs.")
    return {}


def _parse_attempt(value) -> int | None:
    if value is None:
        return None
    try:
        attempt = int(value)
    except Exception:
        return None
    return attempt if attempt > 0 else None


def _stage_dir(kind: str, attempt: int | None) -> str:
    if attempt is None:
        return kind
    return f"{kind}_attempt{attempt}"
