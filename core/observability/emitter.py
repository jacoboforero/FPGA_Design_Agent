"""
Lightweight event emitter to keep observability semantics centralized.
Actual sinks live under adapters/observability/.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from core.observability.events import Event


class EventEmitter:
    def __init__(self, sinks: Optional[Iterable[object]] = None):
        self.sinks: List[object] = list(sinks) if sinks else []

    def emit(self, runtime: str, event_type: str, payload: dict) -> None:
        event = Event(runtime=runtime, event_type=event_type, payload=payload)
        for sink in self.sinks:
            try:
                sink.send(event)
            except Exception:
                # Sinks should be best-effort; never break runtimes.
                continue


_default_emitter = EventEmitter()


def set_global_sinks(sinks: Iterable[object]) -> None:
    global _default_emitter
    _default_emitter = EventEmitter(sinks)


def emit_runtime_event(runtime: str, event_type: str, payload: dict) -> None:
    _default_emitter.emit(runtime=runtime, event_type=event_type, payload=payload)
