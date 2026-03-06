"""
Execution-phase timing metrics recorder and summary writer.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _slug(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in (value or "run"))
    return safe or "run"


def _to_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
    return None


def _ms(start: Any, end: Any) -> Optional[float]:
    s = _to_dt(start)
    e = _to_dt(end)
    if not s or not e:
        return None
    return max(0.0, (e - s).total_seconds() * 1000.0)


def _pct(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    q = max(0.0, min(1.0, q))
    idx = q * (len(ordered) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(ordered[lo])
    frac = idx - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


class ExecutionMetricsRecorder:
    def __init__(self, *, run_id: str | None, run_name: str | None, out_dir: Path | None = None) -> None:
        self.run_id = run_id
        self.run_name = run_name or "run"
        self.records: Dict[str, Dict[str, Any]] = {}
        default_dir = (
            os.getenv("OBSERVABILITY_ARTIFACTS_DIR")
            or os.getenv("AGENTOPS_ARTIFACTS_DIR")
            or "artifacts/observability"
        )
        self.out_dir = Path(out_dir or default_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def ensure_record(self, task_id: str) -> Dict[str, Any]:
        task_key = str(task_id)
        record = self.records.get(task_key)
        if record is None:
            record = {
                "task_id": task_key,
                "run_id": self.run_id,
                "node_id": None,
                "stage_kind": None,
                "attempt": None,
                "task_type": None,
                "runtime": None,
                "published_ts": None,
                "received_ts": None,
                "completed_ts": None,
                "queue_wait_ms": None,
                "service_ms": None,
                "orchestrator_reaction_ms": None,
                "status": None,
            }
            self.records[task_key] = record
        return record

    def record_published(
        self,
        *,
        task_id: str,
        node_id: str,
        stage_kind: str,
        attempt: int | None,
        task_type: str,
        published_ts: datetime,
    ) -> None:
        record = self.ensure_record(task_id)
        record.update(
            {
                "node_id": node_id,
                "stage_kind": stage_kind,
                "attempt": attempt,
                "task_type": task_type,
                "published_ts": published_ts.isoformat(),
            }
        )

    def record_received(self, *, task_id: str, runtime: str | None, received_ts: datetime | None) -> None:
        if not received_ts:
            return
        record = self.ensure_record(task_id)
        record["received_ts"] = received_ts.isoformat()
        if runtime:
            record["runtime"] = runtime

    def record_completed(self, *, task_id: str, completed_ts: datetime | None, status: str | None) -> None:
        if not completed_ts:
            return
        record = self.ensure_record(task_id)
        record["completed_ts"] = completed_ts.isoformat()
        if status:
            record["status"] = status

    def record_reaction(self, *, task_id: str, orchestrator_reaction_ms: float | None) -> None:
        record = self.ensure_record(task_id)
        record["orchestrator_reaction_ms"] = orchestrator_reaction_ms

    def finalize_record(self, task_id: str) -> None:
        record = self.ensure_record(task_id)
        record["queue_wait_ms"] = _ms(record.get("published_ts"), record.get("received_ts"))
        record["service_ms"] = _ms(record.get("received_ts"), record.get("completed_ts"))

    def _summary(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        queue_wait = [float(v) for v in (row.get("queue_wait_ms") for row in rows) if isinstance(v, (int, float))]
        service = [float(v) for v in (row.get("service_ms") for row in rows) if isinstance(v, (int, float))]
        reaction = [
            float(v) for v in (row.get("orchestrator_reaction_ms") for row in rows) if isinstance(v, (int, float))
        ]
        stage_agg: Dict[str, Dict[str, Any]] = {}
        node_totals: Dict[str, float] = {}
        for row in rows:
            stage = str(row.get("stage_kind") or "unknown")
            stage_item = stage_agg.setdefault(stage, {"count": 0, "queue_wait_ms_sum": 0.0, "service_ms_sum": 0.0})
            stage_item["count"] += 1
            if isinstance(row.get("queue_wait_ms"), (int, float)):
                stage_item["queue_wait_ms_sum"] += float(row["queue_wait_ms"])
            if isinstance(row.get("service_ms"), (int, float)):
                stage_item["service_ms_sum"] += float(row["service_ms"])

            node_id = str(row.get("node_id") or "")
            if node_id:
                node_totals.setdefault(node_id, 0.0)
                for key in ("queue_wait_ms", "service_ms", "orchestrator_reaction_ms"):
                    if isinstance(row.get(key), (int, float)):
                        node_totals[node_id] += float(row[key])

        for stage, item in stage_agg.items():
            count = max(1, int(item["count"]))
            item["queue_wait_ms_avg"] = item.pop("queue_wait_ms_sum") / count
            item["service_ms_avg"] = item.pop("service_ms_sum") / count

        critical_node = None
        critical_ms = 0.0
        if node_totals:
            critical_node, critical_ms = max(node_totals.items(), key=lambda kv: kv[1])

        return {
            "task_count": len(rows),
            "queue_wait_ms": {"p50": _pct(queue_wait, 0.50), "p95": _pct(queue_wait, 0.95), "p99": _pct(queue_wait, 0.99)},
            "service_ms": {"p50": _pct(service, 0.50), "p95": _pct(service, 0.95), "p99": _pct(service, 0.99)},
            "orchestrator_reaction_ms": {
                "p50": _pct(reaction, 0.50),
                "p95": _pct(reaction, 0.95),
                "p99": _pct(reaction, 0.99),
            },
            "stage_aggregates": stage_agg,
            "critical_path_estimate": {"node_id": critical_node, "estimated_ms": critical_ms},
        }

    def write(self, *, costs_log_path: str | None = None) -> Path:
        rows = [self.records[key] for key in sorted(self.records.keys())]
        payload = {
            "run_name": self.run_name,
            "run_id": self.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "costs_log_path": costs_log_path,
            "summary": self._summary(rows),
            "tasks": rows,
        }
        path = self.out_dir / f"{_slug(self.run_name)}_execution_metrics.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
