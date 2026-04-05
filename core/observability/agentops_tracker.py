"""
AgentOps-backed observability and cost tracking.

This tracker is a thin shim around the AgentOps SDK. It:
- Initializes AgentOps from env (AGENTOPS_API_KEY or AGENTOPS_ENABLE=1)
- Starts a trace for the current run
- Records LLM call usage/costs into a local JSONL log for repeatability
- Updates AgentOps trace metadata with rolling totals (best-effort)

If AgentOps is not available or not configured, all methods degrade to no-ops.
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from core.runtime.config import get_runtime_config

try:  # Optional dependency
    import agentops
except Exception:  # noqa: BLE001
    agentops = None  # type: ignore

ARTIFACTS_DIR = Path(
    os.getenv("OBSERVABILITY_ARTIFACTS_DIR")
    or os.getenv("AGENTOPS_ARTIFACTS_DIR")
    or "artifacts/observability"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip_text(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _normalize_span_attribute(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    try:
        return _clip_text(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str))
    except Exception:
        return _clip_text(str(value))


def _supports_agentops_openai_auto_instrumentation(llm_provider: str) -> bool:
    provider = str(llm_provider or "").strip().lower()
    if provider != "openai":
        return True
    # AgentOps 0.4.21 still tries to wrap legacy beta chat resources that are
    # absent in current OpenAI SDK builds. Disable only that fragile auto-LLM
    # wrapper path when the compatibility surface is missing so demo output stays
    # clean while our manual cost/trace logging continues to work.
    return importlib.util.find_spec("openai.resources.beta.chat") is not None


class AgentOpsTracker:
    def __init__(self) -> None:
        self.enabled = False
        self.run_id = str(uuid.uuid4())
        self.run_name = "session"
        self._trace_ctx = None
        self._lock = threading.Lock()
        self._totals: Dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "calls": 0,
        }
        self._global_cost_log_path = ARTIFACTS_DIR / "costs.jsonl"
        self._summary_filename = "cost_summary.json"
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    def _slug(self) -> str:
        base = self.run_name or "run"
        safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in base)
        return safe or "run"

    @property
    def summary_path(self) -> Path:
        path = ARTIFACTS_DIR / "runs" / self._slug() / str(self.run_id or "unknown") / "observability" / "summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def legacy_summary_path(self) -> Path:
        return ARTIFACTS_DIR / f"{self._slug()}_summary.json"

    @property
    def latest_summary_path(self) -> Path:
        return ARTIFACTS_DIR / self._summary_filename

    @property
    def cost_log_path(self) -> Path:
        path = ARTIFACTS_DIR / "runs" / self._slug() / str(self.run_id or "unknown") / "observability" / "costs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def legacy_cost_log_path(self) -> Path:
        return self._global_cost_log_path

    def init_from_env(
        self,
        run_name: Optional[str] = None,
        default_tags: Optional[list[str]] = None,
        *,
        run_id: Optional[str] = None,
        force: bool = False,
    ) -> None:
        if self.enabled and not force:
            return
        if self.enabled and force:
            try:
                if agentops is not None:
                    agentops.end_trace()
            except Exception:
                pass
            self.enabled = False
            self._trace_ctx = None
            self._totals = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "calls": 0,
            }
            self.run_id = str(uuid.uuid4())
        self.run_name = run_name or os.getenv("AGENTOPS_RUN_NAME") or "session"
        self.run_id = str(run_id or os.getenv("AGENTOPS_RUN_ID") or self.run_id or uuid.uuid4())

        api_key = os.getenv("AGENTOPS_API_KEY")
        if not api_key and os.getenv("AGENTOPS_ENABLE") != "1":
            return
        if agentops is None:
            return

        tags = default_tags or []
        llm_cfg = get_runtime_config().llm
        llm_provider = llm_cfg.provider
        llm_model = llm_cfg.default_model
        if llm_provider:
            tags.append(f"provider:{llm_provider}")
        if llm_model:
            tags.append(f"model:{llm_model}")

        try:
            instrument_llm_calls = _supports_agentops_openai_auto_instrumentation(llm_provider)
            agentops.init(
                api_key=api_key,
                default_tags=tags,
                instrument_llm_calls=instrument_llm_calls,
                log_level="WARNING",
                fail_safe=True,
                log_session_replay_url=False,
            )
            self._trace_ctx = agentops.start_trace(trace_name=self.run_name, tags=tags)
            # Attach basic metadata to the trace
            agentops.update_trace_metadata({"run_id": self.run_id, "run_name": self.run_name})
            self.enabled = True
        except Exception:
            self.enabled = False

    def log_llm_call(
        self,
        *,
        agent: str,
        node_id: Optional[str],
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost_usd: Optional[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "ts": _now_iso(),
            "run_id": self.run_id,
            "run_name": self.run_name,
            "agent": agent,
            "node_id": node_id,
            "model": model,
            "provider": provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "metadata": metadata or {},
        }
        with self._lock:
            self._totals["prompt_tokens"] += prompt_tokens
            self._totals["completion_tokens"] += completion_tokens
            self._totals["total_tokens"] += total_tokens
            self._totals["estimated_cost_usd"] += float(estimated_cost_usd or 0.0)
            self._totals["calls"] += 1
            for path in (self.cost_log_path, self.legacy_cost_log_path):
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            self._write_summary_locked()
        self.record_llm_span(
            agent=agent,
            node_id=node_id,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            metadata=metadata,
        )
        if self.enabled:
            try:
                agentops.update_trace_metadata(
                    {
                        "last_llm_model": model,
                        "last_llm_provider": provider,
                        "total_prompt_tokens": self._totals["prompt_tokens"],
                        "total_completion_tokens": self._totals["completion_tokens"],
                        "total_tokens": self._totals["total_tokens"],
                        "total_estimated_cost_usd": round(self._totals["estimated_cost_usd"], 6),
                    }
                )
            except Exception:
                pass

    def record_llm_span(
        self,
        *,
        agent: str,
        node_id: Optional[str],
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost_usd: Optional[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            from agentops.semconv import AgentAttributes, SpanAttributes, SpanKind
        except Exception:
            return

        stage = None
        if isinstance(metadata, dict):
            stage = metadata.get("stage")
        operation_name = f"{agent}.{stage}" if stage else str(agent or "llm")
        attrs: Dict[str, Any] = {
            AgentAttributes.AGENT_NAME: agent,
            SpanAttributes.LLM_SYSTEM: provider,
            SpanAttributes.LLM_REQUEST_MODEL: model,
            SpanAttributes.LLM_RESPONSE_MODEL: model,
            SpanAttributes.LLM_USAGE_PROMPT_TOKENS: prompt_tokens,
            SpanAttributes.LLM_USAGE_COMPLETION_TOKENS: completion_tokens,
            SpanAttributes.LLM_USAGE_TOTAL_TOKENS: total_tokens,
            "mhd.node_id": node_id,
            "mhd.run_id": self.run_id,
            "mhd.llm_metadata": metadata or {},
        }
        if estimated_cost_usd is not None:
            attrs[SpanAttributes.LLM_USAGE_TOOL_COST] = round(float(estimated_cost_usd), 6)
        self._record_span(operation_name=operation_name, span_kind=SpanKind.LLM, attributes=attrs)

    def record_runtime_event(self, runtime: str, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            from agentops.semconv import AgentAttributes, SpanKind
        except Exception:
            return

        payload = payload or {}
        attrs: Dict[str, Any] = {
            "mhd.runtime": runtime,
            "mhd.event_type": event_type,
            "mhd.run_id": payload.get("run_id") or self.run_id,
        }
        for key in (
            "task_id",
            "node_id",
            "task_type",
            "agent",
            "status",
            "entity",
            "state",
            "queue_name",
            "worker_instance_id",
            "worker_thread_name",
            "routing_key",
            "reason",
            "max_in_flight",
        ):
            if key in payload:
                attrs[f"mhd.{key}"] = payload.get(key)
        if payload:
            attrs["mhd.payload"] = payload

        span_kind = SpanKind.OPERATION
        if event_type == "state_transition":
            span_kind = SpanKind.WORKFLOW_STEP
        elif event_type == "task_published":
            span_kind = SpanKind.TASK
        elif (
            event_type in {"task_received", "task_result_published"}
            or payload.get("agent")
            or payload.get("task_type")
            or str(runtime).startswith(("worker_", "agent_"))
        ):
            span_kind = SpanKind.AGENT
            attrs[AgentAttributes.AGENT_NAME] = payload.get("agent") or payload.get("task_type") or runtime

        self._record_span(
            operation_name=f"{runtime}.{event_type}",
            span_kind=span_kind,
            attributes=attrs,
        )

    def log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            agentops.update_trace_metadata({f"last_event.{event_type}": json.dumps(payload)})
        except Exception:
            return

    def finalize(self) -> None:
        with self._lock:
            self._write_summary_locked()
        if self.enabled and agentops is not None:
            try:
                agentops.end_trace()
            except Exception:
                pass

    def _write_summary_locked(self) -> None:
        summary = {
            "run_id": self.run_id,
            "run_name": self.run_name,
            "totals": self._totals,
            "updated_at": _now_iso(),
        }
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        self.legacy_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        # Keep a latest pointer for convenience
        self.latest_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def get_totals(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._totals)

    def _record_span(self, *, operation_name: str, span_kind: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled or agentops is None or self._trace_ctx is None:
            return
        root_span = getattr(self._trace_ctx, "span", None)
        if root_span is None:
            return
        try:
            from agentops.sdk.attributes import get_span_attributes
            from agentops.sdk.core import tracer as sdk_tracer
            from opentelemetry import trace as otel_trace
        except Exception:
            return

        normalized_attrs = {
            key: normalized
            for key, value in (attributes or {}).items()
            if (normalized := _normalize_span_attribute(value)) is not None
        }
        try:
            span_attrs = get_span_attributes(
                operation_name=operation_name,
                span_kind=span_kind,
                **normalized_attrs,
            )
            parent_context = otel_trace.set_span_in_context(root_span)
            span_name = f"{operation_name}.{span_kind}"
            span = sdk_tracer.get_tracer().start_span(
                span_name,
                context=parent_context,
                attributes=span_attrs,
            )
            span.end()
        except Exception:
            return


_tracker = AgentOpsTracker()


def get_tracker() -> AgentOpsTracker:
    return _tracker
