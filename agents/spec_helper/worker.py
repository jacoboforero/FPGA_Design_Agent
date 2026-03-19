"""
Specification helper agent runtime.
Receives a draft spec payload, updates the L1-L5 checklist, and reports
which fields are still missing. LLM-only (no heuristic fallback).
"""
from __future__ import annotations

import json
import re
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
        extra_clarifications = _detect_block_diagram_module_gaps(structured, spec_text)
        if extra_clarifications:
            clarifications.extend(extra_clarifications)
        status = "complete" if not clarifications else "needs_clarification"

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


def _detect_block_diagram_module_gaps(checklist: Dict[str, Any], spec_text: str) -> list[str]:
    module_names = _extract_module_names(spec_text)
    module_names_lower = {name.lower() for name in module_names}
    node_ids = []
    l4 = checklist.get("L4") if isinstance(checklist, dict) else None
    block_diagram = l4.get("block_diagram") if isinstance(l4, dict) else None
    if isinstance(block_diagram, list):
        for node in block_diagram:
            if isinstance(node, dict):
                node_id = str(node.get("node_id", "")).strip()
                if node_id:
                    node_ids.append((node_id, bool(node.get("uses_standard_component"))))
    missing_nodes = []
    for node_id, is_std in node_ids:
        if is_std:
            continue
        if module_names_lower and node_id.lower() not in module_names_lower:
            missing_nodes.append(node_id)
    if not missing_nodes:
        return []
    missing_sorted = ", ".join(sorted(set(missing_nodes)))
    return [
        (
            "L4.block_diagram references node_id(s) not defined as Module blocks: "
            f"{missing_sorted}. Add Module sections for these nodes or mark them uses_standard_component=true."
        )
    ]


def _extract_module_names(spec_text: str) -> list[str]:
    names = []
    for match in re.finditer(r"^Module:\s*(.+)$", spec_text, flags=re.MULTILINE):
        name = match.group(1).strip()
        if name:
            names.append(name)
    return names
