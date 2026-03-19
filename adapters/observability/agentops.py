"""
AgentOps sink for EventEmitter. Best-effort: if AgentOps is not configured it
acts as a no-op to avoid impacting runtimes.
"""
from __future__ import annotations

from core.observability.events import Event
from core.observability.agentops_tracker import AgentOpsTracker


class AgentOpsSink:
    def __init__(self, tracker: AgentOpsTracker) -> None:
        self.tracker = tracker

    def send(self, event: Event) -> None:
        # We only forward minimal metadata; detailed LLM cost tracking happens in the tracker.
        if not self.tracker:
            return
        self.tracker.log_event(event.event_type, event.payload)
