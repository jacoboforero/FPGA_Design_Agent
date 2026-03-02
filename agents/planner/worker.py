"""
Planner agent runtime. Consumes PlannerAgent tasks and emits design_context.json + dag.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from agents.common.base import AgentWorkerBase
from core.observability.emitter import emit_runtime_event
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from orchestrator import planner


class PlannerWorker(AgentWorkerBase):
    handled_types = {AgentType.PLANNER}
    runtime_name = "agent_planner"

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context or {}
        spec_dir = Path(ctx.get("spec_dir", "artifacts/task_memory/specs")).resolve()
        out_dir = Path(ctx.get("out_dir", "artifacts/generated")).resolve()
        execution_policy = ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else None
        try:
            planner.generate_from_specs(
                spec_dir=spec_dir,
                out_dir=out_dir,
                execution_policy=execution_policy,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "Pre-plan validation failed" in message:
                lines = [line.strip() for line in message.splitlines() if line.strip()]
                header = lines[0] if lines else "Pre-plan validation failed."
                issue_lines = [line for line in lines[1:] if line.startswith("-")]
                max_issues = 5
                if len(issue_lines) > max_issues:
                    remaining = len(issue_lines) - max_issues
                    issue_lines = issue_lines[:max_issues] + [f"... ({remaining} more issue(s))"]
                message = "\n".join([header] + issue_lines)
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Planner failed: {message}",
            )

        design_context = out_dir / "design_context.json"
        dag_path = out_dir / "dag.json"
        warning_count = 0
        try:
            payload = json.loads(design_context.read_text())
            preplan = payload.get("preplan_validation", {})
            warnings = preplan.get("warnings") if isinstance(preplan, dict) else None
            if isinstance(warnings, list):
                warning_count = len(warnings)
        except Exception:  # noqa: BLE001
            warning_count = 0

        success_log = f"Planner wrote {design_context} and {dag_path}."
        if warning_count:
            success_log = (
                f"Planner wrote {design_context} and {dag_path}. "
                f"Pre-plan validation warnings: {warning_count}."
            )
        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "design_context": str(design_context), "dag": str(dag_path)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(design_context),
            log_output=success_log,
        )
