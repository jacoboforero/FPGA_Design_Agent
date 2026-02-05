"""
Planner agent runtime. Consumes PlannerAgent tasks and emits design_context.json + dag.json.
"""
from __future__ import annotations
import os
from pathlib import Path
from adapters.rag.rag_service import init_rag_service

from agents.common.base import AgentWorkerBase
from core.observability.emitter import emit_runtime_event
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from orchestrator import planner


class PlannerWorker(AgentWorkerBase):
    handled_types = {AgentType.PLANNER}
    runtime_name = "agent_planner"

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context or {}
        
        rag = init_rag_service()
        rag_context_path = None
        if rag is not None:
            query_parts = []
            if ctx.get("user_request"):
                query_parts.append(str(ctx["user_request"]))
            if ctx.get("spec_text"):
                query_parts.append(str(ctx["spec_text"]))
            if ctx.get("node_id"):
                query_parts.append(f"node_id={ctx['node_id']}")
            query = "\n".join(query_parts).strip() or "rtl design planning"
            context_str, _ = rag.retrieve_context(query=query, top_k=int(os.getenv("RAG_TOP_K_PLANNER", "3")))
            out_dir = Path(ctx.get("out_dir", "artifacts/generated")).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            rag_context_path = out_dir / "rag_context.txt"
            rag_context_path.write_text(context_str, encoding="utf-8")
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
