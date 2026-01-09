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

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:  # Optional dependency
    import agentops
except Exception:  # noqa: BLE001
    agentops = None  # type: ignore

ARTIFACTS_DIR = Path("artifacts/observability")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        self.cost_log_path = ARTIFACTS_DIR / "costs.jsonl"
        self._summary_filename = "cost_summary.json"
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    def _slug(self) -> str:
        base = self.run_name or "run"
        safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in base)
        return safe or "run"

    @property
    def summary_path(self) -> Path:
        return ARTIFACTS_DIR / f"{self._slug()}_summary.json"

    @property
    def latest_summary_path(self) -> Path:
        return ARTIFACTS_DIR / self._summary_filename

    def init_from_env(self, run_name: Optional[str] = None, default_tags: Optional[list[str]] = None, force: bool = False) -> None:
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

        api_key = os.getenv("AGENTOPS_API_KEY")
        if not api_key and os.getenv("AGENTOPS_ENABLE") != "1":
            return
        if agentops is None:
            return

        tags = default_tags or []
        llm_provider = os.getenv("LLM_PROVIDER")
        llm_model = os.getenv("OPENAI_MODEL") or os.getenv("GROQ_MODEL")
        if llm_provider:
            tags.append(f"provider:{llm_provider}")
        if llm_model:
            tags.append(f"model:{llm_model}")

        try:
            agentops.init(
                api_key=api_key,
                default_tags=tags,
                instrument_llm_calls=True,
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
            self.cost_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cost_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            self._write_summary_locked()
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
        # Keep a latest pointer for convenience
        self.latest_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def get_totals(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._totals)


_tracker = AgentOpsTracker()


def get_tracker() -> AgentOpsTracker:
    return _tracker
