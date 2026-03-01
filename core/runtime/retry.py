"""
Retry utilities for brokered tasks.
"""
from __future__ import annotations

from typing import Any, Dict
from core.runtime.config import get_runtime_config

# Legacy constant retained for backwards compatibility with external imports.
MAX_RETRIES = 1
RETRY_HEADER = "x-retry-count"


class RetryableError(RuntimeError):
    """Signals a transient error that should be retried once."""


class TaskInputError(RuntimeError):
    """Signals a non-retryable input/schema error (send to DLQ)."""


def get_retry_count(props: Any) -> int:
    headers = getattr(props, "headers", None) or {}
    count = headers.get(RETRY_HEADER, 0)
    try:
        return int(count)
    except Exception:
        return 0


def next_retry_headers(props: Any) -> Dict[str, Any]:
    headers = dict(getattr(props, "headers", None) or {})
    headers[RETRY_HEADER] = get_retry_count(props) + 1
    return headers


def get_max_retries() -> int:
    try:
        return int(get_runtime_config().broker.task_max_retries)
    except Exception:
        return MAX_RETRIES


def is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    tokens = (
        "timeout",
        "timed out",
        "temporar",
        "connection reset",
        "connection aborted",
        "connection refused",
        "rate limit",
        "service unavailable",
    )
    return any(token in text for token in tokens)
