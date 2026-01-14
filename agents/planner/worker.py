"""
Planner agent runtime. Consumes PlannerAgent tasks and emits design_context.json + dag.json.
"""
from __future__ import annotations

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
        try:
            planner.generate_from_specs(spec_dir=spec_dir, out_dir=out_dir)
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Planner failed: {exc}",
            )

        design_context = out_dir / "design_context.json"
        dag_path = out_dir / "dag.json"
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
            log_output=f"Planner wrote {design_context} and {dag_path}.",
        )
