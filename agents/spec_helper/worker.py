"""
Specification helper agent runtime.
Receives a draft spec payload and either confirms completeness or returns
clarifying questions to lock it down. Uses the LLM gateway when enabled,
falls back to a deterministic checklist otherwise.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Tuple

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from core.observability.agentops_tracker import get_tracker


class SpecHelperWorker(AgentWorkerBase):
    handled_types = {AgentType.SPECIFICATION_HELPER}
    runtime_name = "agent_spec_helper"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context or {}
        draft = ctx.get("spec", {})

        seed_structured: Dict[str, Any] = {
            "module_name": draft.get("module_name") or ctx.get("module_name"),
            "spec_text": draft.get("spec_text") or draft.get("behavior") or "",
            "behavior": draft.get("behavior") or draft.get("spec_text") or "",
            "signals": draft.get("signals") or ctx.get("signals") or [],
            "clock": draft.get("clock") or ctx.get("clock"),
            "reset": draft.get("reset") or ctx.get("reset"),
            "coverage_goals": draft.get("coverage_goals") or ctx.get("coverage_goals"),
            "test_plan": draft.get("test_plan") or ctx.get("test_plan"),
            "architecture": draft.get("architecture") or draft.get("architecture_notes") or ctx.get("architecture"),
            "acceptance": draft.get("acceptance") or draft.get("acceptance_criteria") or ctx.get("acceptance"),
        }

        used_llm = False
        llm_payload = None
        if self.gateway and Message:
            try:
                llm_payload = asyncio.run(self._llm_review(seed_structured))
                used_llm = llm_payload is not None
            except Exception:  # noqa: BLE001
                llm_payload = None
                used_llm = False

        if llm_payload:
            structured = {**seed_structured, **(llm_payload.get("structured") or {})}
            clarifications = llm_payload.get("clarifications") or []
            status = llm_payload.get("status") or ("needs_clarification" if clarifications else "complete")
        else:
            status, clarifications, structured = self._fallback_check(seed_structured)

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
            "clarifications": clarifications,
            "structured": structured,
            "used_llm": used_llm,
        }
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=None,
            log_output="\n".join(log_lines),
            reflections=json.dumps(payload),
        )

    async def _llm_review(self, spec: Dict[str, Any]) -> Dict[str, Any] | None:
        system = (
            "You are a hardware specification helper. "
            "Given a free-form spec, decide if it is complete. "
            "Keep L1-L5 style requirements internal; only return concise clarifying questions if something is missing. "
            "Extract structured fields when present: module_name, behavior/spec_text, interface signals (name, direction INPUT/OUTPUT, width), "
            "clock/reset details, coverage goals, test plan notes, architecture/microarchitecture, and acceptance criteria. "
            "Respond with JSON ONLY, no prose, no code fences."
        )
        hints = {
            "module_name": spec.get("module_name"),
            "signals": spec.get("signals"),
            "clock": spec.get("clock"),
            "reset": spec.get("reset"),
            "coverage_goals": spec.get("coverage_goals"),
            "test_plan": spec.get("test_plan"),
            "architecture": spec.get("architecture"),
            "acceptance": spec.get("acceptance"),
        }
        user = (
            "Specification text:\n"
            f"{spec.get('spec_text','')}\n\n"
            "Known structured hints (may be empty):\n"
            f"{json.dumps(hints, indent=2)}\n\n"
            "Return JSON with keys: status ('complete' or 'needs_clarification'), clarifications (list of strings, omit if none), "
            "structured (object mirroring the extracted fields). Do not mention level numbers or internal checklists."
        )
        messages: List[Message] = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_SPEC", os.getenv("LLM_MAX_TOKENS", 800) or 800))
        temperature = float(os.getenv("LLM_TEMPERATURE_SPEC", os.getenv("LLM_TEMPERATURE", 0.2) or 0.2))
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens)
        resp = await self.gateway.generate(messages=messages, config=cfg)  # type: ignore[arg-type]
        tracker = get_tracker()
        try:
            tracker.log_llm_call(
                agent=self.runtime_name,
                node_id=spec.get("module_name"),
                model=getattr(resp, "model_name", "unknown"),
                provider=getattr(resp, "provider", "unknown"),
                prompt_tokens=getattr(resp, "input_tokens", 0),
                completion_tokens=getattr(resp, "output_tokens", 0),
                total_tokens=getattr(resp, "total_tokens", 0),
                estimated_cost_usd=getattr(resp, "estimated_cost_usd", None),
                metadata={"stage": "spec_helper"},
            )
        except Exception:
            pass
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.strip("`")
        parsed = self._safe_json(content)
        return parsed

    def _safe_json(self, text: str) -> Dict[str, Any] | None:
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None

    def _fallback_check(self, spec: Dict[str, Any]) -> Tuple[str, List[str], Dict[str, Any]]:
        clarifications: List[str] = []
        structured = dict(spec)

        if not structured.get("module_name"):
            clarifications.append("What is the module name?")
        if not structured.get("behavior"):
            clarifications.append("Provide a concise behavior/intent description.")
        if not structured.get("signals"):
            clarifications.append("List interface signals (name, direction, width) or share an interface summary.")
        else:
            for sig in structured["signals"]:
                if "name" not in sig or "direction" not in sig:
                    clarifications.append("Each signal needs a name and direction (INPUT/OUTPUT).")
                    break
        if not structured.get("clock") and not structured.get("reset"):
            clarifications.append("Confirm if this is combinational only or provide clock/reset details.")
        if not structured.get("coverage_goals") and not structured.get("test_plan"):
            clarifications.append("Provide coverage goals or a brief test plan (happy/reset/boundary).")
        if not structured.get("architecture"):
            clarifications.append("Add a brief architecture/microarchitecture note (e.g., FSM/datapath outline).")
        if not structured.get("acceptance"):
            clarifications.append("State acceptance criteria (tests pass/coverage thresholds).")

        status = "complete" if not clarifications else "needs_clarification"
        return status, clarifications, structured
