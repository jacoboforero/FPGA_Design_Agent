"""
Helper to wire observability sinks (AgentOps today) from environment settings.
"""
from __future__ import annotations

from typing import Iterable, Optional

from adapters.observability.agentops import AgentOpsSink
from core.observability.agentops_tracker import get_tracker
from core.observability.emitter import set_global_sinks


def configure_observability(run_name: Optional[str] = None, default_tags: Optional[Iterable[str]] = None) -> None:
    tracker = get_tracker()
    tracker.init_from_env(run_name=run_name, default_tags=list(default_tags) if default_tags else [], force=True)
    # Even if not enabled, setting sinks to include a tracker-backed sink is safe (it will no-op).
    set_global_sinks([AgentOpsSink(tracker)])
