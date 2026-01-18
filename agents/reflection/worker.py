"""
Reflection agent runtime. Uses LLM to analyze distilled artifacts and returns insights.
Fails hard if the LLM or distilled dataset is unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from core.schemas.contracts import AgentType, ReflectionInsights, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, init_llm_gateway
from core.observability.agentops_tracker import get_tracker
from core.runtime.retry import RetryableError, TaskInputError, is_transient_error


class ReflectionWorker(AgentWorkerBase):
    handled_types = {AgentType.REFLECTION}
    runtime_name = "agent_reflection"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        if not self.gateway or not Message or not GenerationConfig:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output="LLM gateway unavailable; set USE_LLM=1 and configure provider credentials.",
            )

        ctx = task.context
        if "node_id" not in ctx:
            raise TaskInputError("Missing node_id in task context.")
        node_id = ctx["node_id"]
        distill_path = Path("artifacts/task_memory") / node_id / "distill" / "distilled_dataset.json"
        if not distill_path.exists():
            raise TaskInputError(f"Missing distilled dataset: {distill_path}")

        distill_text = distill_path.read_text()
        system = (
            "You are a Reflection Agent for RTL verification. "
            "Analyze the distilled simulation/log data and produce debugging insights. "
            "Return JSON with keys: hypotheses (list), likely_failure_points (list), "
            "recommended_probes (list), confidence_score (0-1), analysis_notes (string). "
            "Do not include code fences or extra text."
        )
        user = (
            f"Node: {node_id}\n"
            f"Coverage goals: {json.dumps(ctx.get('coverage_goals', {}), indent=2)}\n"
            f"Distilled dataset:\n{distill_text}\n"
        )
        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_REFLECT", "600"))
        temperature = float(os.getenv("LLM_TEMPERATURE_REFLECT", "0.2"))
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens)

        try:
            resp = asyncio.run(self.gateway.generate(messages=msgs, config=cfg))  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            if is_transient_error(exc):
                raise RetryableError(f"Reflection LLM transient error: {exc}")
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Reflection LLM call failed: {exc}",
            )

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

        parsed = _safe_json(resp.content)
        if not parsed:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output="Reflection LLM response was not valid JSON.",
            )
        insights_payload = parsed.get("insights") if isinstance(parsed, dict) else None
        if insights_payload is None and isinstance(parsed, dict):
            insights_payload = parsed
        try:
            insights = ReflectionInsights(**insights_payload)
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Reflection insights invalid: {exc}",
            )

        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={"task_id": str(task.task_id)},
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            log_output=f"Reflection complete via {getattr(resp, 'provider', 'llm')}/{getattr(resp, 'model_name', 'unknown')}.",
            reflection_insights=insights,
        )


def _safe_json(text: str):
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
