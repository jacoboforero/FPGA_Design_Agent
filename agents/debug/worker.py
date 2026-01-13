"""
Debug agent runtime. Consumes debug tasks and proposes concrete fix steps using the LLM.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Tuple

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from core.observability.agentops_tracker import get_tracker


class DebugWorker(AgentWorkerBase):
    handled_types = {AgentType.DEBUG}
    runtime_name = "agent_debug"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context or {}
        node_id = ctx.get("node_id", "unknown")
        reflection = ctx.get("reflection_insights") or {}
        failure_log = ctx.get("failure_log") or ""
        distilled = ctx.get("distilled_dataset") or {}
        rtl_path = ctx.get("rtl_path")
        tb_path = ctx.get("tb_path")

        try:
            if not (self.gateway and Message):
                raise RuntimeError("LLM gateway unavailable; debug agent requires LLM.")
            plan, log_output = asyncio.run(self._llm_debug(node_id, reflection, failure_log, distilled, rtl_path, tb_path))

            emit_runtime_event(
                runtime=self.runtime_name,
                event_type="task_completed",
                payload={"task_id": str(task.task_id)},
            )
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.SUCCESS,
                artifacts_path=None,
                log_output=log_output,
                reflections=json.dumps(plan),
            )
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Debug failed: {exc}",
            )

    async def _llm_debug(
        self,
        node_id: str,
        reflection: Dict[str, Any],
        failure_log: str,
        distilled: Dict[str, Any],
        rtl_path: str | None,
        tb_path: str | None,
    ) -> Tuple[Dict[str, Any], str]:
        system_prompt = (
            "You are a hardware debug agent. Given reflection insights and failure evidence, propose concrete next steps "
            "and minimal code edits to fix the issue. Keep suggestions actionable and concise."
        )
        user_prompt = (
            f"Node: {node_id}\n"
            f"RTL path: {rtl_path or 'unknown'}\n"
            f"TB path: {tb_path or 'unknown'}\n"
            f"Reflection insights:\n{json.dumps(reflection, indent=2)}\n\n"
            f"Failure log excerpt:\n{failure_log or 'n/a'}\n\n"
            f"Distilled dataset: {json.dumps(distilled, indent=2) if distilled else 'n/a'}\n\n"
            "Return JSON with keys: actions (list of prioritized steps), code_edits (list of short patch suggestions), "
            "retest_plan (list of checks to rerun)."
        )
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_DEBUG", os.getenv("LLM_MAX_TOKENS", 800) or 800))
        temperature = float(os.getenv("LLM_TEMPERATURE_DEBUG", os.getenv("LLM_TEMPERATURE", 0.2) or 0.2))
        cfg = GenerationConfig(max_tokens=max_tokens, temperature=temperature, stop_sequences=["```"])
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt), Message(role=MessageRole.USER, content=user_prompt)]
        resp = await self.gateway.generate(messages=messages, config=cfg)  # type: ignore[arg-type]
        tracker = get_tracker()
        try:
            tracker.log_llm_call(
                agent=self.runtime_name,
                node_id=node_id,
                model=getattr(resp, "model_name", "unknown"),
                provider=getattr(resp, "provider", "unknown"),
                prompt_tokens=getattr(resp, "input_tokens", 0),
                completion_tokens=getattr(resp, "output_tokens", 0),
                total_tokens=getattr(resp, "total_tokens", 0),
                estimated_cost_usd=getattr(resp, "estimated_cost_usd", None),
                metadata={"stage": "debug"},
            )
        except Exception:
            pass

        plan = self._safe_json(resp.content)
        if not plan:
            raise RuntimeError("LLM returned unparseable debug plan")
        log_lines = [
            "LLM debug plan:",
            f"Actions: {', '.join(plan.get('actions', [])) if isinstance(plan.get('actions'), list) else plan.get('actions')}",
            f"Code edits: {', '.join(plan.get('code_edits', [])) if isinstance(plan.get('code_edits'), list) else plan.get('code_edits')}",
            f"Retest: {', '.join(plan.get('retest_plan', [])) if isinstance(plan.get('retest_plan'), list) else plan.get('retest_plan')}",
        ]
        return plan, "\n".join([l for l in log_lines if l is not None])

    def _safe_json(self, text: str) -> Dict[str, Any] | None:
        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
            return json.loads(cleaned)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return None
        return None
