"""
Helpers to persist run-scoped artifacts under artifacts/observability/.

Unlike artifacts/task_memory/, these are not purged between CLI runs.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from core.observability.agentops_tracker import ARTIFACTS_DIR, get_tracker


def slugify_run_name(run_name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in (run_name or "run"))
    return safe or "run"


def get_run_artifacts_dir(*, run_name: Optional[str] = None, run_id: Optional[str] = None) -> Path:
    tracker = get_tracker()
    name = run_name or getattr(tracker, "run_name", None) or "run"
    rid = run_id or getattr(tracker, "run_id", None) or "unknown"
    root = ARTIFACTS_DIR / "runs" / slugify_run_name(name) / str(rid)
    root.mkdir(parents=True, exist_ok=True)
    return root


def mirror_directory(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, out)
        except Exception:
            try:
                out.write_bytes(path.read_bytes())
            except Exception:
                continue
