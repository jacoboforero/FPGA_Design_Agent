"""
Reflection agent runtime. Consumes ReflectionAgent tasks and synthesizes
structured insights from failure logs / distilled datasets using an LLM.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Tuple

from core.schemas.contracts import AgentType, ReflectionInsights, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig
from core.observability.agentops_tracker import get_tracker

MAX_LOG_CHARS = 1600


class ReflectionWorker(AgentWorkerBase):
    handled_types = {AgentType.REFLECTION}
    runtime_name = "agent_reflection"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        try:
            ctx = task.context or {}
            node_id = ctx.get("node_id", "unknown")
            failure_log = (ctx.get("failure_log") or "")[:MAX_LOG_CHARS]
            distilled = ctx.get("distilled_dataset") or {}
            interface = ctx.get("interface", {}).get("signals", [])
            extras = {"rtl_path": ctx.get("rtl_path"), "tb_path": ctx.get("tb_path"), "failure_log_path": ctx.get("failure_log_path")}

            if not (self.gateway and Message):
                raise RuntimeError("LLM gateway unavailable; reflection agent requires LLM.")
            insights, log_output = asyncio.run(self._llm_reflect(node_id, interface, failure_log, distilled))

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
                reflection_insights=insights,
                reflections=json.dumps({"extras": extras}),
            )
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                artifacts_path=None,
                log_output=f"Reflection failed: {exc}",
            )

    async def _llm_reflect(
        self, node_id: str, interface: list[Dict[str, Any]], failure_log: str, distilled: Dict[str, Any]
    ) -> Tuple[ReflectionInsights, str]:
        system_prompt = (
            "You are a hardware reflection/debugging agent. Given an RTL/TB simulation failure log and distilled data summary, "
            "produce concise hypotheses and probes. Avoid verbose prose. Return JSON ONLY with keys:\n"
            "hypotheses (list of strings), likely_failure_points (list), recommended_probes (list), confidence_score (0-1), analysis_notes (short text)."
        )
        distilled_snip = json.dumps(distilled, indent=2) if distilled else "{}"
        iface_lines = "\n".join(f"- {s.get('direction','')}: {s.get('name','')} [{s.get('width',1)}]" for s in interface)
        user_prompt = (
            f"Node: {node_id}\n"
            f"Interface:\n{iface_lines or 'n/a'}\n\n"
            f"Distilled dataset:\n{distilled_snip}\n\n"
            f"Failure log excerpt (trimmed to {MAX_LOG_CHARS} chars):\n{failure_log or 'no log captured'}\n\n"
            "Return JSON only. Focus on plausible root causes and specific probes (signals/conditions) to validate."
        )
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_REFLECT", os.getenv("LLM_MAX_TOKENS", 800) or 800))
        temperature = float(os.getenv("LLM_TEMPERATURE_REFLECT", os.getenv("LLM_TEMPERATURE", 0.2) or 0.2))
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
                metadata={"stage": "reflection"},
            )
        except Exception:
            pass
        parsed = self._safe_json(resp.content)
        if not parsed:
            raise RuntimeError("LLM returned unparseable reflection output")
        return self._to_insights(parsed), f"LLM reflection via {getattr(resp, 'provider', 'llm')}/{getattr(resp, 'model_name', 'unknown')}"

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

    def _to_insights(self, payload: Dict[str, Any]) -> ReflectionInsights:
        return ReflectionInsights(
            hypotheses=payload.get("hypotheses") or [],
            likely_failure_points=payload.get("likely_failure_points") or [],
            recommended_probes=payload.get("recommended_probes") or [],
            confidence_score=float(payload.get("confidence_score", 0.5)),
            analysis_notes=payload.get("analysis_notes") or "LLM reflection output",
        )
