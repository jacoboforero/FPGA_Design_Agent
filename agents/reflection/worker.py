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
        attempt = _parse_attempt(ctx.get("attempt"))
        distill_path = Path("artifacts/task_memory") / node_id / _stage_dir("distill", attempt) / "distilled_dataset.json"
        if not distill_path.exists():
            raise TaskInputError(f"Missing distilled dataset: {distill_path}")

        distill_text = distill_path.read_text()
        rtl_path = Path(ctx.get("rtl_path", "")) if ctx.get("rtl_path") else Path("artifacts/generated/rtl") / f"{node_id}.sv"
        tb_path = Path(ctx.get("tb_path", "")) if ctx.get("tb_path") else rtl_path.with_name(f"{node_id}_tb.sv")
        rtl_text = rtl_path.read_text() if rtl_path.exists() else f"<<RTL missing at {rtl_path}>>"
        tb_text = tb_path.read_text() if tb_path.exists() else f"<<TB missing at {tb_path}>>"
        system = (
            "You are a Reflection Agent for RTL verification. "
            "Analyze the distilled simulation/log data and the full RTL/TB code to produce debugging insights. "
            "Return JSON with keys: hypotheses (list of strings), likely_failure_points (list of strings), "
            "recommended_probes (list of strings), confidence_score (0-1), analysis_notes (string). "
            "Do NOT return objects inside the lists; every list entry must be a plain string. "
            "Evidence anchoring is required: each hypothesis and likely_failure_point MUST include a bracketed "
            "evidence citation referencing the provided data (e.g., [evidence: log_excerpt L12 'FAIL: ...'], "
            "[evidence: waveform_excerpt signal=tb.dut.count time=6000], "
            "[evidence: RTL L42 'always @(posedge clk...)']). "
            "If evidence is insufficient, state that explicitly in the analysis_notes. "
            "Do not include code fences or extra text."
        )
        user = (
            f"Node: {node_id}\n"
            f"Coverage goals: {json.dumps(ctx.get('coverage_goals', {}), indent=2)}\n"
            f"Distilled dataset:\n{distill_text}\n\n"
            f"RTL source (full, line-numbered):\n{_number_lines(rtl_text)}\n\n"
            f"Testbench source (full, line-numbered):\n{_number_lines(tb_text)}\n"
        )
        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]
        max_tokens = int(os.getenv("LLM_MAX_TOKENS_REFLECT", "10000"))
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
        if isinstance(insights_payload, dict):
            insights_payload = _normalize_reflection_payload(insights_payload)
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


def _parse_attempt(value) -> int | None:
    if value is None:
        return None
    try:
        attempt = int(value)
    except Exception:
        return None
    return attempt if attempt > 0 else None


def _stage_dir(kind: str, attempt: int | None) -> str:
    if attempt is None:
        return kind
    return f"{kind}_attempt{attempt}"


def _number_lines(text: str) -> str:
    lines = text.splitlines()
    width = len(str(len(lines))) if lines else 1
    return "\n".join(f"{idx+1:>{width}}: {line}" for idx, line in enumerate(lines))


def _normalize_reflection_payload(payload: dict) -> dict:
    normalized = dict(payload)
    for key in ("hypotheses", "likely_failure_points", "recommended_probes"):
        normalized[key] = _normalize_list_field(normalized.get(key))
    return normalized


def _normalize_list_field(value) -> list[str]:
    items: list[str] = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return items
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                items.append(text)
            continue
        if isinstance(item, dict):
            text = None
            for key in ("hypothesis", "point", "item", "text", "summary", "detail", "statement"):
                if key in item and isinstance(item[key], str):
                    text = item[key].strip()
                    break
            if text is None:
                for val in item.values():
                    if isinstance(val, str):
                        text = val.strip()
                        break
            if text is None:
                text = json.dumps(item, ensure_ascii=True)
            evidence = None
            for key in ("evidence", "citation", "citations", "source", "sources"):
                if key in item:
                    ev = item[key]
                    if isinstance(ev, str):
                        evidence = ev.strip()
                    elif isinstance(ev, list):
                        ev_items = [e.strip() for e in ev if isinstance(e, str) and e.strip()]
                        if ev_items:
                            evidence = "; ".join(ev_items)
                    break
            if evidence and "[evidence:" not in text:
                text = f"{text} [evidence: {evidence}]"
            items.append(text)
            continue
        items.append(str(item))
    return items
