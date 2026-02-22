"""
Simulation worker. Runs iverilog/vvp and fails hard if tools are missing.
Tool discovery and command construction driven by tool_registry.yaml
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
from core.runtime.retry import (
        RetryableError,
        TaskInputError,
        get_retry_count,
        next_retry_headers,
        MAX_RETRIES,
)

from core.tools.registry import ToolRegistry, get_registry

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"

#--------------------------------------------
# Worker
#--------------------------------------------

class SimulationWorker(threading.Thread):
    def __init__(
            self,
            connection_params: pika.ConnectionParameters,
            stop_event: threading.Event,
            registry: ToolRegistry | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self._registry = registry or get_registry()

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
#-----------------------------------------------------------------------------
# Task Handling
#-----------------------------------------------------------------------------

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        rtl_path = ctx.get("rtl_path")
        tb_path = ctx.get("tb_path")
        node_id = ctx.get("node_id")
        attempt = _parse_attempt(ctx.get("attempt"))

       # Resolve tools from registry -----------------------------------------
        try:
            iverilog = self._registry.get("iverilog")
            vvp = self._registry.get("vvp")
        except FileNotFoundError as exc:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=str(exc),
            )

        sources = list(dict.fromkeys(rtl_paths))
        if tb_path:
            sources.append(tb_path)

        log_lines: list[str] = []

        # Build ---------------------------------------------------------------
        build_result = _run_build(iverilog, sources, log_lines)
        if build_result is not None:           # compilation failed
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="\n".join(log_lines),
            )

        # Simulate ------------------------------------------------------------
        run_ok, run_output = _run_simulation(vvp, log_lines)
        if not run_ok:
            cycle, time_val = _extract_failure_info(run_output)
            _append_analysis(log_lines, cycle, time_val)

            artifacts_path = None
            if vvp.can("supports_dump"):
                rerun_info = _maybe_rerun_with_dump(
                    vvp=vvp,
                    node_id=node_id,
                    attempt=attempt,
                    cycle=cycle,
                    log_lines=log_lines,
                    sim_cfg=self._registry.simulation,
                )
                if rerun_info.get("waveform_path"):
                    artifacts_path = rerun_info["waveform_path"]

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
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=None,
            log_output="\n".join(log_lines),
        )

    def _publish_result(
            self,
            ch: pika.adapters.blocking_connection.BlockingChannel,
            result: ResultMessage,
    ) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )


# ---------------------------------------------------------------------------
# Build / run helpers
# ---------------------------------------------------------------------------

_SIM_BINARY = "/tmp/sim.out"


def _run_build(iverilog, sources: list[str], log_lines: list[str]) -> subprocess.CompletedProcess | None:
    """Compile sources with iverilog. Returns the process on failure, None on success."""
    spec = iverilog.cmd("build")
    cmd = spec.build(
        tool=iverilog.resolved_path,
        output=_SIM_BINARY,
        sources=" ".join(sources),
    )
    log_lines.append("[build]")
    log_lines.append(f"cmd: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        log_lines.append(f"Build timeout: {exc}")
        return exc  # truthy → caller treats as failure
    if proc.returncode != 0:
        output = "\n".join(p for p in [proc.stdout, proc.stderr] if p).strip()
        if output:
            log_lines.append(output)
        return proc
    return None


def _run_simulation(vvp, log_lines: list[str]) -> tuple[bool, str]:
    """Run the compiled simulation binary. Returns (success, combined_output)."""
    spec = vvp.cmd("run")
    cmd = spec.build(tool=vvp.resolved_path, binary=_SIM_BINARY)
    log_lines.append("[run]")
    log_lines.append(f"cmd: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        log_lines.append(f"Simulation timeout: {exc}")
        return False, ""
    output = "\n".join(p for p in [proc.stdout, proc.stderr] if p).strip()
    if output:
        log_lines.append(output)
    else:
        log_lines.append("Simulation passed.")
    failed = proc.returncode != 0 or _has_failure_marker(output)
    return not failed, output


def _append_analysis(log_lines: list[str], cycle: int | None, time_val: int | None) -> None:
    log_lines.append("[analysis]")
    if cycle is not None or time_val is not None:
        cycle_msg = str(cycle) if cycle is not None else "unknown"
        time_msg = str(time_val) if time_val is not None else "unknown"
        log_lines.append(f"Detected failure cycle={cycle_msg} time={time_msg}.")
    else:
        log_lines.append("No failure cycle/time found in log output.")


def _maybe_rerun_with_dump(
    *,
    vvp,
    node_id: str | None,
    attempt: int | None,
    cycle: int | None,
    log_lines: list[str],
    sim_cfg,
) -> dict:
    log_lines.append("[rerun]")
    if not node_id:
        log_lines.append("Skipping waveform rerun (missing node_id in context).")
        return {}
    if cycle is None:
        log_lines.append(
            "Skipping waveform rerun (failure cycle not found; enable cycle logging in testbench)."
        )
        return {}

    before = sim_cfg.fail_window_before
    after = sim_cfg.fail_window_after
    start_cycle = max(0, cycle - before)
    end_cycle = cycle + after

    waveform_path = (
        Path(sim_cfg.artifact_base)
        / node_id
        / _stage_dir("sim", attempt)
        / sim_cfg.waveform_filename
    )
    waveform_path.parent.mkdir(parents=True, exist_ok=True)

    # Build window args — omit DUMP_START when start_cycle == 0 to avoid
    # benches that interpret DUMP_START=0 as "disabled".
    use_window = start_cycle > 0
    window_args = (
        f"+DUMP_START={start_cycle} +DUMP_END={end_cycle}" if use_window else ""
    )

    spec = vvp.cmd("run_with_dump")
    cmd = spec.build(
        tool=vvp.resolved_path,
        binary=_SIM_BINARY,
        waveform_path=waveform_path,
        window_args=window_args,
    )
    # Remove empty strings that result from empty window_args
    cmd = [part for part in cmd if part]

    if use_window:
        log_lines.append(f"Re-running for waveform capture (cycles {start_cycle}..{end_cycle}).")
    else:
        log_lines.append(
            "Re-running for waveform capture from cycle 0 "
            "(window omitted; DUMP_START=0 can break some benches)."
        )
    log_lines.append(f"cmd: {' '.join(cmd)}")

    try:
        rerun = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        log_lines.append(f"Waveform rerun failed: {exc}")
        return {}

    rerun_output = "\n".join(p for p in [rerun.stdout, rerun.stderr] if p).strip()
    if rerun_output:
        log_lines.append(rerun_output)

    if waveform_path.exists():
        log_lines.append(f"Waveform written to {waveform_path}.")
        return {"waveform_path": str(waveform_path)}

    log_lines.append("Waveform not generated; testbench may not support dump plusargs.")
    return {}


# ---------------------------------------------------------------------------
# Pattern matching helpers
# ---------------------------------------------------------------------------

_FAIL_CYCLE_RE = re.compile(r"\bcycle\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_TIME_RE = re.compile(r"\btime\b\s*=?\s*(\d+)", re.IGNORECASE)
_FAIL_MARKER_RE = re.compile(r"\b(FAIL|ERROR)\b", re.IGNORECASE)


def _extract_failure_info(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    lines = text.splitlines()
    candidates = [l for l in lines if "FAIL" in l or "ERROR" in l] or lines
    cycle = time_val = None
    for line in candidates:
        if cycle is None and (m := _FAIL_CYCLE_RE.search(line)):
            cycle = int(m.group(1))
        if time_val is None and (m := _FAIL_TIME_RE.search(line)):
            time_val = int(m.group(1))
        if cycle is not None and time_val is not None:
            break
    return cycle, time_val


def _has_failure_marker(text: str | None) -> bool:
    return bool(text and _FAIL_MARKER_RE.search(text))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_attempt(value) -> int | None:
    if value is None:
        return None
    try:
        attempt = int(value)
        return attempt if attempt > 0 else None
    except Exception:
        return None


def _stage_dir(kind: str, attempt: int | None) -> str:
    return kind if attempt is None else f"{kind}_attempt{attempt}"
