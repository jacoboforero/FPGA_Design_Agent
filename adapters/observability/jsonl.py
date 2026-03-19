"""
JSONL sink for local observability logs.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class JsonlFileSink:
    def __init__(self, run_name: str, run_id: str, base_dir: Path | None = None) -> None:
        self.run_name = run_name or "run"
        self.run_id = run_id
        self.base_dir = Path(base_dir or "artifacts/observability")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / f"{self._slug()}_events.jsonl"
        self._lock = threading.Lock()
        self.path.touch(exist_ok=True)

    def _slug(self) -> str:
        safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in self.run_name)
        return safe or "run"

    def send(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        entry = {
            "ts": getattr(event, "timestamp", None).isoformat() if getattr(event, "timestamp", None) else None,
            "run_id": self.run_id,
            "run_name": self.run_name,
            "runtime": getattr(event, "runtime", None),
            "event_type": getattr(event, "event_type", None),
            "payload": payload,
        }
        line = json.dumps(entry, ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
