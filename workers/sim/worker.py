"""
Simulation worker. Runs iverilog/vvp and fails hard if tools are missing.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pika
from core.schemas.contracts import ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import RetryableError, TaskInputError, get_max_retries, get_retry_count, next_retry_headers
from core.runtime.broker import DEFAULT_RESULTS_ROUTING_KEY, TASK_EXCHANGE, resolve_task_queue
from core.runtime.config import get_runtime_config


class SimulationWorker(threading.Thread):
    queue_name = resolve_task_queue("SimulatorWorker") or "simulation_tasks"

    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self.worker_instance_id = f"worker_sim:{id(self):x}"

    def run(self) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.basic_qos(prefetch_count=1)
            for method, props, body in ch.consume(self.queue_name, inactivity_timeout=0.5):
                if self.stop_event.is_set():
                    break
                if body is None:
                    continue
                try:
                    task = TaskMessage.model_validate_json(body)
                except Exception:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                received_at = datetime.now(timezone.utc)
                emit_runtime_event(
                    runtime="worker_sim",
                    event_type="task_received",
                    payload={
                        "task_id": str(task.task_id),
                        "node_id": task.context.get("node_id"),
                        "task_type": task.task_type.value,
                        "run_id": task.run_id,
                        "received_ts": received_at.isoformat(),
                        "worker_instance_id": self.worker_instance_id,
                        "worker_thread_name": self.name,
                        "queue_name": self.queue_name,
                    },
                )
                try:
                    result = self.handle_task(task)
                except TaskInputError:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                except RetryableError:
                    retry_count = get_retry_count(props)
                    if retry_count < get_max_retries():
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
                result = result.model_copy(
                    update={
                        "received_at": result.received_at or received_at,
                        "started_at": result.started_at or received_at,
                    }
                )
                self._publish_result(ch, task, result)
                emit_runtime_event(
                    runtime="worker_sim",
                    event_type="task_result_published",
                    payload={
                        "task_id": str(task.task_id),
                        "node_id": task.context.get("node_id"),
                        "task_type": task.task_type.value,
                        "status": result.status.value,
                        "run_id": task.run_id,
                        "worker_instance_id": self.worker_instance_id,
                        "worker_thread_name": self.name,
                        "queue_name": self.queue_name,
                    },
                )
                ch.basic_ack(method.delivery_tag)

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        runtime_cfg = get_runtime_config()
        iverilog = runtime_cfg.tools.iverilog_path or shutil.which("iverilog")
        vvp = runtime_cfg.tools.vvp_path or shutil.which("vvp")
        rtl_path = task.context.get("rtl_path")
        tb_path = task.context.get("tb_path")
        oracle_ref_path = task.context.get("oracle_ref_path")
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
        oracle_ref = None
        if oracle_ref_path:
            oracle_ref = Path(str(oracle_ref_path))
            if not oracle_ref.exists():
                raise TaskInputError(f"Oracle reference RTL missing: {oracle_ref}")
        try:
            sources = list(dict.fromkeys(rtl_paths))
            if tb_path:
                sources.append(tb_path)
            if oracle_ref is not None:
                sources.append(str(oracle_ref))
            sources = list(dict.fromkeys(sources))
            stage_dir = Path("artifacts/task_memory") / str(node_id or "node") / _stage_dir("sim", attempt)
            stage_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=f"sim_{str(node_id or 'node')}_") as tmpdir:
                workdir = Path(tmpdir)
                sim_bin = workdir / "sim.out"
                cmd = [iverilog, "-g2012", "-g2005-sv", "-o", str(sim_bin), *sources]
                log_lines = []
                log_lines.append("[build]")
                log_lines.append(f"cmd: {' '.join(cmd)}")
                log_lines.append(f"cwd: {workdir}")
                build = _run_subprocess(cmd, timeout=30, cwd=workdir)
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
                run_cmd = [vvp, str(sim_bin)]
                run = _run_subprocess(run_cmd, timeout=30, cwd=workdir)
                run_output = "\n".join(part for part in [run.stdout, run.stderr] if part).strip()
                ctx = task.context if isinstance(task.context, dict) else {}
                execution_policy = ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else {}
                verification_scope = str(ctx.get("verification_scope", "")).strip()
                benchmark_mode = bool(execution_policy.get("benchmark_mode")) or verification_scope == "oracle_compare"
                has_failure_marker = _has_failure_marker(run_output)
                benchmark_failure_reason = _benchmark_failure_reason(run_output) if benchmark_mode else None
                if run.returncode != 0 or has_failure_marker or benchmark_failure_reason:
                    log_lines.append("[run]")
                    log_lines.append(f"cmd: {' '.join(run_cmd)}")
                    log_lines.append(f"cwd: {workdir}")
                    if run_output:
                        log_lines.append(run_output)
                    cycle, time_val = _extract_failure_info(run_output)
                    log_lines.append("[analysis]")
                    if run.returncode != 0:
                        log_lines.append(f"Simulation failed (exit code {run.returncode}).")
                    elif benchmark_failure_reason:
                        log_lines.append(
                            f"Benchmark oracle comparison reported failure ({benchmark_failure_reason}); treating as failure."
                        )
                    else:
                        log_lines.append("Simulation reported failure marker in output; treating as failure.")
                    if cycle is not None or time_val is not None:
                        cycle_msg = str(cycle) if cycle is not None else "unknown"
                        time_msg = str(time_val) if time_val is not None else "unknown"
                        log_lines.append(f"Detected failure cycle={cycle_msg} time={time_msg}.")
                    else:
                        log_lines.append("No failure cycle/time found in log output.")

                    artifacts_path = None
                    rerun_log = _maybe_rerun_with_dump(
                        vvp=vvp,
                        sim_bin=sim_bin,
                        node_id=node_id,
                        attempt=attempt,
                        cycle=cycle,
                        log_lines=log_lines,
                        workdir=workdir,
                        stage_dir=stage_dir,
                    )
                    if rerun_log.get("waveform_path"):
                        artifacts_path = rerun_log["waveform_path"]

                    # Preserve plain wave.vcd produced by benches so debugging can inspect it.
                    wave_vcd = workdir / "wave.vcd"
                    if wave_vcd.exists():
                        default_wave = stage_dir / "wave.vcd"
                        try:
                            shutil.copy2(wave_vcd, default_wave)
                            if artifacts_path is None:
                                artifacts_path = str(default_wave)
                        except Exception:
                            pass

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
                log_lines.append(f"cwd: {workdir}")
                if run_output:
                    log_lines.append(run_output)
                else:
                    log_lines.append("Simulation passed.")

                artifacts_path = None
                wave_vcd = workdir / "wave.vcd"
                if wave_vcd.exists():
                    default_wave = stage_dir / "wave.vcd"
                    try:
                        shutil.copy2(wave_vcd, default_wave)
                        artifacts_path = str(default_wave)
                    except Exception:
                        artifacts_path = None

                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.SUCCESS,
                    artifacts_path=artifacts_path,
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

    def _publish_result(
        self,
        ch: pika.adapters.blocking_connection.BlockingChannel,
        task: TaskMessage,
        result: ResultMessage,
    ) -> None:
        routed = result.model_copy(update={"run_id": result.run_id or task.run_id})
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=task.results_routing_key or DEFAULT_RESULTS_ROUTING_KEY,
            body=routed.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


_FAIL_CYCLE_RE = re.compile(r"\bcycle\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_TIME_RE = re.compile(r"\btime\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_MARKER_RE = re.compile(r"\b(FAIL|FAILURE|ERROR|FATAL|ASSERT|ASSERTION)\b", re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"\bTIMEOUT\b", re.IGNORECASE)
_MISMATCH_RE = re.compile(r"\bMismatches:\s*(\d+)\b", re.IGNORECASE)


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


def _benchmark_failure_reason(text: str | None) -> str | None:
    if not text:
        return None
    reasons: list[str] = []
    if _TIMEOUT_RE.search(text):
        reasons.append("timeout reported by benchmark harness")
    mismatch_match = _MISMATCH_RE.search(text)
    if mismatch_match:
        mismatch_count = int(mismatch_match.group(1))
        if mismatch_count > 0:
            reasons.append(f"nonzero mismatches={mismatch_count}")
    if not reasons:
        return None
    return "; ".join(reasons)


def _maybe_rerun_with_dump(
    *,
    vvp: str,
    sim_bin: Path,
    node_id: str | None,
    attempt: int | None,
    cycle: int | None,
    log_lines: list[str],
    workdir: Path,
    stage_dir: Path,
) -> dict:
    if not node_id:
        log_lines.append("[rerun]")
        log_lines.append("Skipping waveform rerun (missing node_id in context).")
        return {}
    if cycle is None:
        log_lines.append("[rerun]")
        log_lines.append("Skipping waveform rerun (failure cycle not found; enable cycle logging in testbench).")
        return {}

    sim_cfg = get_runtime_config().sim
    before = int(sim_cfg.fail_window_before)
    after = int(sim_cfg.fail_window_after)
    start_cycle = max(0, cycle - before)
    end_cycle = cycle + after
    waveform_path = stage_dir / "waveform.vcd"
    waveform_path.parent.mkdir(parents=True, exist_ok=True)

    # Many benches gate dumping with $dumpoff/$dumpon and (incorrectly) treat DUMP_START=0 as "disabled".
    # If we want to start at cycle 0, omit DUMP_START/DUMP_END entirely so the bench dumps from time 0.
    use_window = start_cycle > 0
    rerun_cmd = [vvp, str(sim_bin), "+DUMP", f"+DUMP_FILE={waveform_path}"]
    if use_window:
        rerun_cmd.extend([f"+DUMP_START={start_cycle}", f"+DUMP_END={end_cycle}"])
    log_lines.append("[rerun]")
    if use_window:
        log_lines.append(f"Re-running for waveform capture (cycles {start_cycle}..{end_cycle}).")
    else:
        log_lines.append("Re-running for waveform capture from cycle 0 (window omitted; DUMP_START=0 can break some benches).")
    log_lines.append(f"cmd: {' '.join(rerun_cmd)}")
    log_lines.append(f"cwd: {workdir}")
    try:
        rerun = _run_subprocess(rerun_cmd, timeout=30, cwd=workdir)
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


def _run_subprocess(cmd: list[str], *, timeout: float, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if cwd is not None:
        kwargs["cwd"] = str(cwd)
    try:
        return subprocess.run(cmd, **kwargs)
    except TypeError:
        # Test doubles in unit tests may not accept cwd kwarg.
        kwargs.pop("cwd", None)
        return subprocess.run(cmd, **kwargs)
