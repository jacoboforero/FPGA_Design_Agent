"""
Debug agent runtime. Uses LLM to propose fixes based on task memory logs.
Fails hard if the LLM or inputs are unavailable.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus
from core.observability.emitter import emit_runtime_event
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, init_llm_gateway
from core.observability.agentops_tracker import get_tracker
from core.runtime.retry import RetryableError, TaskInputError, is_transient_error


class DebugWorker(AgentWorkerBase):
    handled_types = {AgentType.DEBUG}
    runtime_name = "agent_debug"

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
        log_bundle = _collect_task_logs(node_id)
        if not log_bundle:
            raise TaskInputError(f"No task memory logs found for node {node_id}.")

        system = (
            "You are a Debug Agent for RTL designs. "
            "Propose targeted fixes based on the logs. "
            "Return JSON with keys: summary, suggested_changes (list), risks (list), "
            "next_steps (list). Do not include code fences."
        )
        user = (
            f"Node: {node_id}\n"
            f"Context:\n{json.dumps(ctx, indent=2)}\n\n"
            f"Task logs:\n{log_bundle}\n"
        )
        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_DEBUG", "700"))
        temperature = float(os.getenv("LLM_TEMPERATURE_DEBUG", "0.2"))
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens)

        try:
            resp = asyncio.run(self.gateway.generate(messages=msgs, config=cfg))  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            if is_transient_error(exc):
                raise RetryableError(f"Debug LLM transient error: {exc}")
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Debug LLM call failed: {exc}",
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
                metadata={"stage": "debug"},
            )
        except Exception:
            pass

        parsed = _safe_json(resp.content)
        if not parsed:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output="Debug LLM response was not valid JSON.",
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
            artifacts_path=None,
            log_output=resp.content,
            reflections=json.dumps(parsed, indent=2),
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


def _collect_task_logs(node_id: str) -> str:
    base = Path("artifacts/task_memory") / node_id
    if not base.exists():
        return ""
    logs = []
    for stage in sorted(base.iterdir()):
        log_path = stage / "log.txt"
        if log_path.exists():
            logs.append(f"[{stage.name}]\n{log_path.read_text().strip()}")
    return "\n\n".join(logs)
