"""
Deterministic lint worker. Runs Verilator lint and fails hard on errors.
Tool discovery and lint config are driven by tool_registry.yaml
"""
from __future__ import annotations

import os
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


class LintWorker(threading.Thread):
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
            for method, props, body in ch.consume("process_tasks", inactivity_timeout=0.5):
                if self.stop_event.is_set():
                    break
                if body is None:
                    continue
                try:
                    task = TaskMessage.model_validate_json(body)
                except Exception:
                    ch.basic_nack(method.delivery_tag, requeue=False)
                    continue
                # Skip non-lint tasks
                if task.task_type.value != "LinterWorker":
                    ch.basic_nack(method.delivery_tag, requeue=True)
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
                        log_output=f"Unhandled lint error: {exc}",
                    )
                self._publish_result(ch, result)
                ch.basic_ack(method.delivery_tag)
#----------------------------------------------------------------------
# Task Handling
#----------------------------------------------------------------------


    def handle_task(self, task: TaskMessage) -> ResultMessage:
        if "rtl_path" not in task.context:
            raise TaskInputError("Missing rtl_path in task context.")
        rtl_path = Path(task.context["rtl_path"])
        rtl_paths = task.context.get("rtl_paths") or [str(rtl_path)]
        if not isinstance(rtl_paths, list):
            rtl_paths = [str(rtl_path)]
        rtl_paths = [str(path) for path in rtl_paths if path]
        if not rtl_paths:
            raise TaskInputError("Missing rtl_paths in task context.")
        missing_rtl = [path for path in rtl_paths if not Path(path).exists()]
        if missing_rtl:
            raise TaskInputError(f"RTL missing: {missing_rtl}")
        
        # Resolve tool and config from registry --------------------------------
        try:
            verilator = self._registry.get("verilator")
        except FileNotFoundError as exc:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=str(exc),
            )
        lint_cfg = self._registry.lint

        # Run lint -------------------------------------------------------------
        sources = list(dict.fromkeys(rtl_paths))
        try:
            log, passed = _run_lint(verilator, sources, lint_cfg.strict_warnings)
        except RetryableError:
            raise
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Verilator failed: {exc}",
            )

        if not passed:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=log,
            )



        emit_runtime_event(
            runtime="worker_lint",
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "artifacts_path": str(rtl_path)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(rtl_path),
            log_output=log,
        )

    def _publish_result(
            self,
            ch: pika.adapters.blocking_connection.BlockingChannel, 
            result: ResultMessage
    ) -> None:
        
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )

# ---------------------------------------------------------------------------
# Lint helper
# ---------------------------------------------------------------------------

def _run_lint(verilator, sources: list[str], strict_warnings: bool) -> tuple[str, bool]:
    """
    Run verilator --lint-only.

    Returns (log_output, passed).
    Raises RetryableError on timeout so the worker loop can handle retries.
    """
    spec = verilator.cmd("lint")
    cmd = spec.build(tool=verilator.resolved_path, sources=" ".join(sources))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RetryableError(f"Verilator timeout: {exc}") from exc

    output = ((proc.stderr or "") + (proc.stdout or "")).strip()

    error_marker: str = verilator.can("error_marker") or "%Error"
    fatal_marker: str = verilator.can("fatal_marker") or "%Fatal"
    has_error = (error_marker in output) or (fatal_marker in output)

    if proc.returncode != 0 and (strict_warnings or has_error):
        return output or "Verilator lint failed.", False

    if proc.returncode != 0 and not has_error and not strict_warnings:
        log = output or "Verilator lint passed (non-fatal warnings)."
    else:
        log = output or "Verilator lint passed."

    return log, True
