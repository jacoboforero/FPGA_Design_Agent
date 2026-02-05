"""
Finalizer / RAG-Archiver agent runtime (AI-enhanced).

Runs ONLY after the RTL pipeline succeeds and:
1) snapshots the final RTL/TB + key logs into a run bundle folder
2) writes a manifest.json for traceability
3) calls an LLM once to produce a structured "design historian" summary (final_summary.json)
4) stores + indexes a normalized "final design" record into VerilogRAGService long-term memory

This lets other agents call RAG and retrieve the best prior successful designs.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, init_llm_gateway
from core.observability.agentops_tracker import get_tracker
from core.observability.emitter import emit_runtime_event
from core.runtime.retry import TaskInputError
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus

# IMPORTANT: adjust this import path if your RAG service lives elsewhere
from adapters.rag.rag_service import init_rag_service  # type: ignore


_MODULE_HEADER_WITH_PORTS = re.compile(
    r"\bmodule\s+([A-Za-z_]\w*)\s*(?:#\s*\(.*?\)\s*)?\(\s*(.*?)\s*\)\s*;",
    re.DOTALL,
)
_MODULE_HEADER_NO_PORTS = re.compile(r"\bmodule\s+([A-Za-z_]\w*)\s*;", re.DOTALL)


def _safe_json(text: str) -> Optional[dict]:
    """Parse JSON safely; also tries to extract the first {...} block if extra text is present."""
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            return None
    return None


def _read_text(path: Path) -> str:
    try:
        if path and path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    return ""


def _sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _parse_attempt(value) -> int | None:
    if value is None:
        return None
    try:
        attempt = int(value)
    except Exception:
        return None
    return attempt if attempt > 0 else None


def _stage_dir(kind: str, attempt: int | None) -> str:
    if attempt is None:
        return kind
    return f"{kind}_attempt{attempt}"


def _extract_signature_and_module_name(rtl_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (signature, module_name). Signature is a normalized one-line module header if possible.
    """
    m = _MODULE_HEADER_WITH_PORTS.search(rtl_text)
    if m:
        module_name = m.group(1)
        port_block = " ".join(m.group(2).split())
        signature = f"module {module_name}({port_block});"
        return signature, module_name

    m2 = _MODULE_HEADER_NO_PORTS.search(rtl_text)
    if m2:
        module_name = m2.group(1)
        signature = f"module {module_name};"
        return signature, module_name

    return None, None


def _build_rag_text(
    *,
    module_name: str,
    signature: str,
    summary: str,
    interface_signals: Optional[list],
    verification: Optional[dict],
    node_id: str,
    attempt: int | None,
    rtl_sha: str,
    tb_sha: str,
    run_id: str,
) -> str:
    """
    Single text blob that embeddings index well. Keep stable/compact.
    """
    lines: list[str] = []
    lines.append("// FINAL DESIGN (PASSING RUN)")
    lines.append(f"// run_id: {run_id}")
    lines.append(f"// node_id: {node_id}")
    lines.append(f"// attempt: {attempt if attempt is not None else 'unknown'}")
    lines.append(f"// module: {module_name}")
    lines.append(f"// signature: {signature}")
    lines.append(f"// summary: {summary}")
    lines.append(f"// rtl_sha256: {rtl_sha}")
    lines.append(f"// tb_sha256: {tb_sha}")

    if interface_signals:
        lines.append("// interface_signals:")
        for s in interface_signals[:64]:
            try:
                nm = s.get("name")
                dr = s.get("direction")
                wd = s.get("width", 1)
                lines.append(f"// - {dr} {nm} width={wd}")
            except Exception:
                continue

    if verification:
        lines.append("// verification:")
        goals = verification.get("goals") if isinstance(verification, dict) else None
        if isinstance(goals, list) and goals:
            for g in goals[:32]:
                lines.append(f"// - goal: {str(g)}")
        elif isinstance(verification, dict):
            lines.append(f"// keys={sorted(list(verification.keys()))}")

    return "\n".join(lines) + "\n"


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _short_hash(text: str, n: int = 10) -> str:
    return sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _tail(text: str, n: int) -> str:
    if not text:
        return ""
    return text[-n:]


class FinalizerWorker(AgentWorkerBase):
    """
    Runs after the pipeline succeeds and archives a passing design into:
    - artifacts/rag_runs/... (bundle + manifest)
    - RAG long-term memory json + vector index (via VerilogRAGService)
    Also calls an LLM once to generate a structured summary for better retrieval.
    """

    handled_types = {AgentType.FINALIZE}  # must exist in your AgentType enum
    runtime_name = "agent_finalizer"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.rag = init_rag_service()
        self.gateway = init_llm_gateway()

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context or {}

        # Required fields
        if "node_id" not in ctx:
            raise TaskInputError("Missing node_id in task context.")
        if "rtl_path" not in ctx:
            raise TaskInputError("Missing rtl_path in task context.")

        node_id = str(ctx["node_id"])
        attempt = _parse_attempt(ctx.get("attempt"))

        rtl_path = Path(ctx["rtl_path"])
        tb_path = Path(ctx.get("tb_path", "")) if ctx.get("tb_path") else rtl_path.with_name(f"{node_id}_tb.sv")

        # Read final sources
        rtl_text = _read_text(rtl_path)
        tb_text = _read_text(tb_path)

        if not rtl_text.strip():
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Finalizer missing RTL contents at {rtl_path}",
            )
        if not tb_text.strip():
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Finalizer missing TB contents at {tb_path}",
            )

        signature, module_name = _extract_signature_and_module_name(rtl_text)
        if not module_name:
            module_name = node_id
        if not signature:
            signature = f"module {module_name}(/* unknown */);"

        # Optional artifacts from task_memory
        task_memory_root = Path("artifacts/task_memory") / node_id
        sim_log = _read_text(task_memory_root / _stage_dir("sim", attempt) / "log.txt")
        lint_log = _read_text(task_memory_root / _stage_dir("lint", attempt) / "log.txt")
        tb_lint_log = _read_text(task_memory_root / _stage_dir("tb_lint", attempt) / "log.txt")
        reflection = _read_text(task_memory_root / _stage_dir("reflect", attempt) / "reflection_insights.json")
        distilled = _read_text(task_memory_root / _stage_dir("distill", attempt) / "distilled_dataset.json")

        # Hashes
        rtl_sha = _sha256_text(rtl_text)
        tb_sha = _sha256_text(tb_text)

        # Build bundle directory
        ts = _utc_now_compact()
        run_id = f"{node_id}__{ts}__attempt{attempt if attempt is not None else 'x'}__{_short_hash(rtl_sha + tb_sha)}"
        bundle_root = Path("artifacts/rag_runs") / node_id / run_id
        logs_dir = bundle_root / "logs"
        insights_dir = bundle_root / "insights"
        bundle_root.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        insights_dir.mkdir(parents=True, exist_ok=True)

        # Write bundle files (always)
        (bundle_root / "rtl.sv").write_text(rtl_text, encoding="utf-8")
        (bundle_root / "tb.sv").write_text(tb_text, encoding="utf-8")

        interface = None
        if isinstance(ctx.get("interface"), dict) and isinstance(ctx["interface"].get("signals"), list):
            interface = {"signals": ctx["interface"]["signals"]}
            (bundle_root / "interface.json").write_text(json.dumps(interface, indent=2), encoding="utf-8")

        verification = ctx.get("verification") if isinstance(ctx.get("verification"), dict) else None
        if verification is not None:
            (bundle_root / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")

        # Save logs/insights if present
        if lint_log.strip():
            (logs_dir / "lint.log").write_text(lint_log, encoding="utf-8")
        if tb_lint_log.strip():
            (logs_dir / "tb_lint.log").write_text(tb_lint_log, encoding="utf-8")
        if sim_log.strip():
            (logs_dir / "sim.log").write_text(sim_log, encoding="utf-8")
        if distilled.strip():
            (insights_dir / "distilled_dataset.json").write_text(distilled, encoding="utf-8")
        if reflection.strip():
            (insights_dir / "reflection_insights.json").write_text(reflection, encoding="utf-8")

        # ----------------------------
        # AI Summary (Design Historian)
        # ----------------------------
        ai_summary: Optional[dict] = None
        ai_log = "LLM summary skipped (gateway disabled/unavailable)."

        if self.gateway and os.getenv("USE_LLM", "1") == "1":
            ai_summary = self._llm_summarize(
                node_id=node_id,
                module_name=module_name,
                signature=signature,
                rtl_text=rtl_text,
                tb_text=tb_text,
                sim_log=sim_log,
                reflection=reflection,
                verification=verification,
                interface_signals=(interface or {}).get("signals") if interface else None,
            )
            if ai_summary:
                (bundle_root / "final_summary.json").write_text(json.dumps(ai_summary, indent=2), encoding="utf-8")
                ai_log = "LLM summary created (final_summary.json)."
            else:
                ai_log = "LLM summary attempted but invalid/empty JSON; continuing without AI summary."

        # Summary string used for manifest + RAG
        summary = str(ctx.get("final_summary") or "").strip()
        if not summary and ai_summary and isinstance(ai_summary.get("design_summary"), str):
            summary = ai_summary["design_summary"].strip()
        if not summary:
            summary = f"{module_name}: Final passing design archived for reuse."

        # Manifest
        manifest: Dict[str, Any] = {
            "schema_version": "1.1",
            "run_id": run_id,
            "node_id": node_id,
            "timestamp_utc": ts,
            "attempt": attempt,
            "dut_name": module_name,
            "signature": signature,
            "summary": summary,
            "hashes": {"rtl_sha256": rtl_sha, "tb_sha256": tb_sha},
            "bundle_root": str(bundle_root),
            "ai_summary_path": str(bundle_root / "final_summary.json") if (bundle_root / "final_summary.json").exists() else None,
            "artifacts": {
                "rtl_path": str(bundle_root / "rtl.sv"),
                "tb_path": str(bundle_root / "tb.sv"),
                "logs": {
                    "lint": str(logs_dir / "lint.log") if (logs_dir / "lint.log").exists() else None,
                    "tb_lint": str(logs_dir / "tb_lint.log") if (logs_dir / "tb_lint.log").exists() else None,
                    "sim": str(logs_dir / "sim.log") if (logs_dir / "sim.log").exists() else None,
                },
                "insights": {
                    "distilled": str(insights_dir / "distilled_dataset.json") if (insights_dir / "distilled_dataset.json").exists() else None,
                    "reflection": str(insights_dir / "reflection_insights.json") if (insights_dir / "reflection_insights.json").exists() else None,
                },
                "interface": str(bundle_root / "interface.json") if (bundle_root / "interface.json").exists() else None,
                "verification": str(bundle_root / "verification.json") if (bundle_root / "verification.json").exists() else None,
            },
            "outcome": {"status": "SUCCESS"},
            "notes": {"ai": ai_log},
        }
        (bundle_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        
        rag_log = "RAG disabled or unavailable; skipping indexing."
        if self.rag is not None:
            rag_text = _build_rag_text(
                module_name=module_name,
                signature=signature,
                summary=summary,
                interface_signals=(interface or {}).get("signals") if interface else None,
                verification=verification,
                node_id=node_id,
                attempt=attempt,
                rtl_sha=rtl_sha,
                tb_sha=tb_sha,
                run_id=run_id,
            )

            # Make sure update_memory() can detect a module header.
            # Include signature + AI summary JSON + rag_text for better retrieval.
            assistant_output_for_rag = (
                f"{summary}\n"
                f"{signature}\n"
                f"{json.dumps(ai_summary, indent=2) if ai_summary else ''}\n"
                f"{rag_text}\n"
            )
            user_input_for_rag = f"ARCHIVE FINAL PASSING DESIGN node={node_id} run_id={run_id}"

            inserted = self.rag.update_memory(user_input_for_rag, assistant_output_for_rag)
            if inserted:
                rag_log = f"RAG stored + indexed: {inserted}"
            else:
                rag_log = "RAG: design already present or no modules detected; manifest saved anyway."

            # Helpful debug record in the bundle
            try:
                extra_record = {
                    "module_name": module_name,
                    "signature": signature,
                    "summary": summary,
                    "run_id": run_id,
                    "node_id": node_id,
                    "attempt": attempt,
                    "timestamp_utc": ts,
                    "rtl_sha256": rtl_sha,
                    "tb_sha256": tb_sha,
                    "ai_summary": ai_summary,
                    "rag_text": rag_text,
                    "bundle_root": str(bundle_root),
                }
                (bundle_root / "rag_record.json").write_text(json.dumps(extra_record, indent=2), encoding="utf-8")
            except Exception:
                pass

        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={"task_id": str(task.task_id), "run_id": run_id, "bundle_root": str(bundle_root)},
        )

        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(bundle_root),
            log_output=f"Finalizer archived run_id={run_id}. {ai_log} {rag_log}",
            reflections=json.dumps(
                {
                    "run_id": run_id,
                    "bundle_root": str(bundle_root),
                    "dut_name": module_name,
                    "signature": signature,
                    "rtl_sha256": rtl_sha,
                    "tb_sha256": tb_sha,
                    "ai": ai_log,
                    "rag": rag_log,
                },
                indent=2,
            ),
        )

    def _llm_summarize(
        self,
        *,
        node_id: str,
        module_name: str,
        signature: str,
        rtl_text: str,
        tb_text: str,
        sim_log: str,
        reflection: str,
        verification: Optional[dict],
        interface_signals: Optional[list],
    ) -> Optional[dict]:
        """One LLM call to produce a structured, reusable summary for RAG."""
        if not self.gateway:
            return None

        system = (
            "You are an RTL Finalizer Agent.\n"
            "A design has PASSED simulation. Produce a compact, high-signal summary that helps future agents reuse it.\n"
            "Return ONLY valid JSON (no extra text, no code fences).\n"
            "Schema (exact keys):\n"
            "{\n"
            '  "design_summary": string,\n'
            '  "interface_overview": [{"name": string, "direction": "input"|"output", "width": string}],\n'
            '  "key_behaviors": [string],\n'
            '  "verification_strategy": [string],\n'
            '  "reusable_patterns": [string],\n'
            '  "assumptions_and_limits": [string]\n'
            "}\n"
            "Rules:\n"
            "- Do NOT invent ports; infer from RTL only.\n"
            "- Keep each list item <= 1 sentence.\n"
            "- If logs/insights are missing, mention that in assumptions_and_limits.\n"
            "- Focus on what matters for reuse.\n"
        )

        # Keep prompt size manageable
        rtl_clip = rtl_text if len(rtl_text) <= 12000 else rtl_text[:12000] + "\n// [truncated]\n"
        tb_clip = tb_text if len(tb_text) <= 12000 else tb_text[:12000] + "\n// [truncated]\n"
        sim_tail = _tail(sim_log, 4000)
        refl_tail = _tail(reflection, 4000)

        user = (
            f"node_id: {node_id}\n"
            f"module_name: {module_name}\n"
            f"signature: {signature}\n\n"
            f"known_interface_signals (may be partial): {json.dumps(interface_signals or [], indent=2)}\n\n"
            f"verification_context (may be partial): {json.dumps(verification or {}, indent=2)}\n\n"
            "FINAL RTL:\n"
            f"{rtl_clip}\n\n"
            "FINAL TESTBENCH:\n"
            f"{tb_clip}\n\n"
            "SIM LOG (tail):\n"
            f"{sim_tail}\n\n"
            "REFLECTION INSIGHTS (tail):\n"
            f"{refl_tail}\n"
        )

        msgs = [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ]

        max_tokens = int(os.getenv("LLM_MAX_TOKENS_FINALIZER", "2500"))
        temperature = float(os.getenv("LLM_TEMPERATURE_FINALIZER", "0.2"))
        cfg = GenerationConfig(temperature=temperature, max_tokens=max_tokens)

        try:
            resp = asyncio.run(self.gateway.generate(messages=msgs, config=cfg))  # type: ignore[arg-type]
        except Exception:
            return None

        # Track LLM usage (optional, matches your other agents)
        try:
            tracker = get_tracker()
            tracker.log_llm_call(
                agent=self.runtime_name,
                node_id=node_id,
                model=getattr(resp, "model_name", "unknown"),
                provider=getattr(resp, "provider", "unknown"),
                prompt_tokens=getattr(resp, "input_tokens", 0),
                completion_tokens=getattr(resp, "output_tokens", 0),
                total_tokens=getattr(resp, "total_tokens", 0),
                estimated_cost_usd=getattr(resp, "estimated_cost_usd", None),
                metadata={"stage": "finalizer_summary"},
            )
        except Exception:
            pass

        parsed = _safe_json(getattr(resp, "content", "") or "")
        if not parsed:
            return None

        # Basic sanity checks
        if not isinstance(parsed.get("design_summary", ""), str):
            return None
        if not isinstance(parsed.get("key_behaviors", []), list):
            return None
        if not isinstance(parsed.get("verification_strategy", []), list):
            return None

        return parsed
