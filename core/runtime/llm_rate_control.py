"""
Adaptive in-flight concurrency guard for LLM calls.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

from core.observability.emitter import emit_runtime_event
from core.runtime.config import get_runtime_config


def _error_text(exc: Exception) -> str:
    return str(exc or "").strip().lower()


def _is_backoff_error(exc: Exception) -> bool:
    text = _error_text(exc)
    if not text:
        return False
    triggers = ("429", "rate limit", "ratelimit", "too many requests", "timeout", "timed out")
    return any(trigger in text for trigger in triggers)


@dataclass
class _Ticket:
    acquired_at: float


class LlmRateController:
    def __init__(self) -> None:
        self._lock = threading.Condition()
        self._in_flight = 0
        self._max_current = 4
        self._max_min = 1
        self._max_max = 8
        self._adaptive = True
        self._backoff_on_429 = True
        self._success_streak = 0
        self._last_backoff_at = 0.0
        self._sync_from_config()

    def _sync_from_config(self) -> None:
        cfg = get_runtime_config().llm.rate_control
        self._adaptive = bool(cfg.adaptive_enabled)
        self._backoff_on_429 = bool(cfg.backoff_on_429)
        self._max_min = max(1, int(cfg.max_in_flight_min))
        self._max_max = max(self._max_min, int(cfg.max_in_flight_max))
        default = int(cfg.max_in_flight_default)
        default = max(self._max_min, min(self._max_max, default))
        if self._in_flight == 0:
            self._max_current = default
        else:
            self._max_current = max(self._max_min, min(self._max_max, self._max_current))

    def acquire(self) -> _Ticket:
        self._sync_from_config()
        with self._lock:
            while self._in_flight >= self._max_current:
                self._lock.wait(timeout=0.05)
                self._sync_from_config()
            self._in_flight += 1
            return _Ticket(acquired_at=time.time())

    def release(self, ticket: _Ticket, *, error: Optional[Exception] = None) -> None:
        _ = ticket
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._sync_from_config()

            if error is not None:
                self._success_streak = 0
                if self._adaptive and self._backoff_on_429 and _is_backoff_error(error):
                    previous = self._max_current
                    self._max_current = max(self._max_min, self._max_current - 1)
                    self._last_backoff_at = time.time()
                    if self._max_current != previous:
                        emit_runtime_event(
                            runtime="llm_rate_control",
                            event_type="max_in_flight_changed",
                            payload={
                                "reason": "backoff",
                                "max_in_flight": self._max_current,
                                "error": str(error),
                            },
                        )
            else:
                self._success_streak += 1
                if not self._adaptive:
                    self._lock.notify()
                    return
                now = time.time()
                cooldown_s = 5.0
                threshold = max(8, self._max_current * 2)
                if (
                    self._success_streak >= threshold
                    and self._max_current < self._max_max
                    and (now - self._last_backoff_at) >= cooldown_s
                ):
                    self._success_streak = 0
                    self._max_current += 1
                    emit_runtime_event(
                        runtime="llm_rate_control",
                        event_type="max_in_flight_changed",
                        payload={
                            "reason": "recovery",
                            "max_in_flight": self._max_current,
                        },
                    )
            self._lock.notify()


_CONTROLLER: LlmRateController | None = None
_CONTROLLER_LOCK = threading.Lock()


def get_llm_rate_controller() -> LlmRateController:
    global _CONTROLLER
    if _CONTROLLER is not None:
        return _CONTROLLER
    with _CONTROLLER_LOCK:
        if _CONTROLLER is None:
            _CONTROLLER = LlmRateController()
    return _CONTROLLER

