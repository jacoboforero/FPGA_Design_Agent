"""
Specification helper agent runtime.
Receives a draft spec payload, updates the L1-L5 checklist, and reports
which fields are still missing. LLM-only (no heuristic fallback).
"""
from __future__ import annotations

import json
from typing import Any, Dict

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway
from agents.spec_helper.checklist import build_empty_checklist, list_missing_fields
from agents.spec_helper.llm_helper import update_checklist_from_spec


class SpecHelperWorker(AgentWorkerBase):
    handled_types = {AgentType.SPECIFICATION_HELPER}
    runtime_name = "agent_spec_helper"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context or {}
        draft = ctx.get("spec", {}) if isinstance(ctx.get("spec"), dict) else {}
        spec_text = draft.get("spec_text") or draft.get("behavior") or ctx.get("spec_text") or ""
        checklist = draft.get("checklist") if isinstance(draft.get("checklist"), dict) else build_empty_checklist()

        if not self.gateway:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output="LLM is required for spec helper (set USE_LLM=1 and provider keys).",
                reflections=json.dumps({"status": "failed", "reason": "llm_unavailable"}),
            )

        structured = update_checklist_from_spec(self.gateway, spec_text, checklist)
        missing = list_missing_fields(structured)
        clarifications = [field.path for field in missing]
        status = "complete" if not missing else "needs_clarification"

        log_lines = []
        if clarifications:
            log_lines.append("Spec is incomplete; clarify the following:")
            log_lines.extend(f"- {q}" for q in clarifications)
        else:
            log_lines.append("Spec appears complete and can be locked.")

        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={"task_id": str(task.task_id)},
        )
        payload = {
            "status": status,
            "missing_fields": clarifications,
            "checklist": structured,
        }
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=None,
            log_output="\n".join(log_lines),
            reflections=json.dumps(payload),
        )
