"""
Specification helper agent runtime.
Receives a draft spec payload and either confirms completeness or returns
clarifying questions to lock it down. LLM-only: no deterministic fallback.
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
        try:
            if not (self.gateway and Message):
                raise RuntimeError("LLM gateway unavailable for spec helper (USE_LLM must be enabled).")
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

            llm_payload, raw_content = asyncio.run(self._llm_review(seed_structured))
            if not llm_payload or not isinstance(llm_payload, dict):
                raise RuntimeError(f"LLM returned no structured output for spec helper. Raw response: {raw_content}")
            if llm_payload.get("structured_raw") and not llm_payload.get("structured"):
                raise RuntimeError(f"LLM response was not valid JSON. Raw response: {raw_content}")
            structured = {**seed_structured, **(llm_payload.get("structured") or {})}
            if not structured and llm_payload.get("structured_raw"):
                structured = {**seed_structured, "structured_raw": llm_payload["structured_raw"]}
            clarifications = llm_payload.get("clarifications") or []
            status = llm_payload.get("status") or ("needs_clarification" if clarifications else "complete")

            log_lines = []
            if status == "invalid":
                log_lines.append("Spec appears invalid or unrelated to hardware. Please provide a hardware design spec.")
            elif clarifications:
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
                "used_llm": True,
            }
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.SUCCESS,
                artifacts_path=None,
                log_output="\n".join(log_lines),
                reflections=json.dumps(payload),
            )
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Spec helper failed: {exc}",
            )

    async def _llm_review(self, spec: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, str]:
        system = (
            "You are a hardware specification helper. Given a free-form hardware spec, you must:\n"
            "1) Interpret the raw spec text and extract structured fields for the L1-L5 checklist.\n"
            "2) INFER as much as possible (clock/reset names, ready/valid signals, widths, FIFO depths, goals, and any module-to-module wiring/connection intent if a system is described) from the text; only ask for truly missing or ambiguous items.\n"
            "3) If the text is clearly not a hardware design spec, mark status='invalid' and add a concise request for a valid hardware spec.\n"
            "Keep the L1-L5 checklist internal. Return JSON ONLY (no prose, no code fences) with keys:\n"
            "- status: 'complete', 'needs_clarification', or 'invalid'\n"
            "- clarifications: list of concise questions for remaining gaps ONLY (omit/empty if none). When something is missing, offer the user two options: provide it directly or ask you to draft it for them.\n"
            "- structured: {\n"
            "    module_name,\n"
            "    spec_text,\n"
            "    behavior,\n"
            "    signals: [{name, direction (INPUT/OUTPUT), width}],\n"
            "    clock: {name} if sequential else {},\n"
            "    reset: {name, active_low: bool, asynchronous: bool} if applicable else {},\n"
            "    coverage_goals: {branch,toggle} if provided,\n"
            "    test_plan: list of scenarios/notes,\n"
            "    architecture: str,\n"
            "    acceptance: str,\n"
            "    connection_intent: [{from_module, from_port, to_module, to_port, notes}] when a system with multiple modules is described\n"
            "  }\n"
            "Avoid redundant questions; assume ready/valid semantics if mentioned; reuse names and widths from the text."
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
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens, stop_sequences=["```"])

        async def _once(msgs: List[Message]) -> Tuple[Dict[str, Any] | None, str, Any]:
            resp_inner = await self.gateway.generate(messages=msgs, config=cfg)  # type: ignore[arg-type]
            raw_inner = resp_inner.content.strip()
            if raw_inner.startswith("```"):
                raw_inner = raw_inner.strip("`")
            parsed_inner = self._safe_json(raw_inner)
            return parsed_inner, raw_inner, resp_inner

        parsed, raw, last_resp = await _once(messages)
        if parsed is None:
            # Retry once with explicit JSON-only instruction
            retry_msgs = messages + [
                Message(
                    role=MessageRole.USER,
                    content="Previous response was not valid JSON. Return ONLY JSON with the same keys (status, clarifications, structured) and no extra text.",
                )
            ]
            parsed, raw, last_resp = await _once(retry_msgs)

        tracker = get_tracker()
        try:
            tracker.log_llm_call(
                agent=self.runtime_name,
                node_id=spec.get("module_name"),
                model=getattr(last_resp, "model_name", "unknown"),
                provider=getattr(last_resp, "provider", "unknown"),
                prompt_tokens=getattr(last_resp, "input_tokens", 0),
                completion_tokens=getattr(last_resp, "output_tokens", 0),
                total_tokens=getattr(last_resp, "total_tokens", 0),
                estimated_cost_usd=getattr(last_resp, "estimated_cost_usd", None),
                metadata={"stage": "spec_helper"},
            )
        except Exception:
            pass
        return parsed, raw

    def _safe_json(self, text: str) -> Dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
        # direct JSON load
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed[0]
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # try to extract first balanced JSON object
        frag = self._extract_first_json_object(cleaned)
        if frag:
            for loader in (json.loads, self._ast_load):
                try:
                    parsed = loader(frag)
                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                        return parsed[0]
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        # final fallback: wrap raw as structured_raw so caller can inspect
        return {"structured_raw": text}

    def _extract_first_json_object(self, text: str) -> str | None:
        in_string = False
        escape = False
        depth = 0
        start_idx = None
        for idx, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
            if in_string:
                continue
            if ch == "{":
                if depth == 0:
                    start_idx = idx
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start_idx is not None:
                        return text[start_idx : idx + 1]
        return None

    def _ast_load(self, frag: str) -> Any:
        import ast

        return ast.literal_eval(frag)
