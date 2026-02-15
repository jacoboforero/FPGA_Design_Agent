"""
Deterministic lint worker. Runs Verilator lint and fails hard on errors.
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


_EDGE_ALWAYS_RE = re.compile(r"always\s*@\s*\(([^)]*(?:posedge|negedge)[^)]*)\)", re.IGNORECASE | re.DOTALL)


def _run_rtl_semantic_lint(
    *,
    rtl_text: str,
    module_contract: dict | None,
) -> list[str]:
    if not isinstance(module_contract, dict):
        return []
    issues: list[str] = []
    style = str(module_contract.get("style", "")).strip().lower()

    if style == "combinational" or module_contract.get("forbid_edge_always"):
        for match in _EDGE_ALWAYS_RE.finditer(rtl_text):
            line = rtl_text.count("\n", 0, match.start()) + 1
            issues.append(
                f"RLSEM001 L{line}: combinational contract violated by edge-sensitive always block: always @({match.group(1).strip()})."
            )

    if module_contract.get("prefer_debug_passthrough"):
        debug_outputs = module_contract.get("debug_outputs")
        if isinstance(debug_outputs, list):
            for raw_name in debug_outputs:
                name = str(raw_name).strip()
                if not name:
                    continue
                pattern = re.compile(
                    rf"always\s*@\s*\([^)]*(?:posedge|negedge)[^)]*\)[\s\S]*?\b{re.escape(name)}\b\s*(?:<=|=)",
                    re.IGNORECASE,
                )
                match = pattern.search(rtl_text)
                if match:
                    line = rtl_text.count("\n", 0, match.start()) + 1
                    issues.append(
                        f"RLSEM010 L{line}: integration contract prefers direct passthrough for debug output '{name}', but it is assigned in a sequential block."
                    )
    return sorted(set(issues))


def _format_semantic_issues(issues: list[str]) -> str:
    return "\n".join(f"- {issue}" for issue in issues)


def _format_semantic_failure_log(issues: list[str], compile_log: str) -> str:
    base = (
        "RTL semantic lint failed.\n"
        "[rtl_semantic] FAIL\n"
        f"{_format_semantic_issues(issues)}"
    )
    compile_log = (compile_log or "").strip()
    if compile_log:
        base += f"\n[compile]\n{compile_log}"
    return base


class LintWorker(threading.Thread):
    def __init__(self, connection_params: pika.ConnectionParameters, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.connection_params = connection_params
        self.stop_event = stop_event
        self.verilator = os.getenv("VERILATOR_PATH") or shutil.which("verilator")

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

        if not self.verilator:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="Verilator not found; set VERILATOR_PATH or install verilator.",
            )
        strict_warnings = os.getenv("VERILATOR_STRICT_WARNINGS", "0") == "1"
        fail_moddup = os.getenv("RTL_LINT_FAIL_MODDUP", "1") != "0"
        semantic_enabled = os.getenv("RTL_LINT_SEMANTIC", "1") != "0"
        semantic_strict = os.getenv("RTL_LINT_SEMANTIC_STRICT", "1") != "0"
        try:
            rtl_args = list(dict.fromkeys(rtl_paths))
            cmd = [self.verilator, "--lint-only", "--quiet", "--sv", *rtl_args]
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = (completed.stderr or "") + (completed.stdout or "")
            output = output.strip()
            has_moddup = "MODDUP" in output.upper()
            has_error = ("%Error" in output) or ("%Fatal" in output)
            if has_moddup and fail_moddup:
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=None,
                    log_output=output or "Verilator lint failed: duplicate module declarations (MODDUP).",
                )
            if completed.returncode != 0 and (strict_warnings or has_error):
                return ResultMessage(
                    task_id=task.task_id,
                    correlation_id=task.correlation_id,
                    status=TaskStatus.FAILURE,
                    artifacts_path=None,
                    log_output=output or "Verilator lint failed.",
                )
            if completed.returncode != 0 and not has_error and not strict_warnings:
                log = output or "Verilator lint passed (non-fatal warnings)."
            else:
                log = output or "Verilator lint passed."

            semantic_issues: list[str] = []
            if semantic_enabled:
                semantic_issues = _run_rtl_semantic_lint(
                    rtl_text=rtl_path.read_text(),
                    module_contract=task.context.get("module_contract") if isinstance(task.context, dict) else None,
                )
                if semantic_issues and semantic_strict:
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        status=TaskStatus.FAILURE,
                        artifacts_path=None,
                        log_output=_format_semantic_failure_log(semantic_issues, output),
                    )
                if semantic_issues:
                    log = f"{log.rstrip()}\n[rtl_semantic] WARN\n{_format_semantic_issues(semantic_issues)}".strip()
                else:
                    log = f"{log.rstrip()}\n[rtl_semantic] PASS".strip()
        except subprocess.TimeoutExpired as exc:
            raise RetryableError(f"Verilator timeout: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Verilator failed: {exc}",
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

    def _publish_result(self, ch: pika.adapters.blocking_connection.BlockingChannel, result: ResultMessage) -> None:
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=RESULTS_ROUTING_KEY,
            body=result.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
