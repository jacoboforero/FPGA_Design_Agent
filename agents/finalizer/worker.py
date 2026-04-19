"""
Finalizer agent runtime.

Runs after acceptance succeeds to archive the passing design and update RAG
memory for future runs.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from adapters.rag.rag_service import archive_final_design, default_archive_root
from agents.common.base import AgentWorkerBase
from agents.common.llm_gateway import GenerationConfig, Message, MessageRole, apply_reproducibility_settings, init_llm_gateway
from core.observability.agentops_tracker import get_tracker
from core.observability.emitter import emit_runtime_event
from core.prompting import apply_prompt_output_contract, build_prompt_metadata, render_prompt, write_prompt_trace
from core.runtime.config import get_runtime_config
from core.runtime.paths import task_memory_root
from core.runtime.retry import TaskInputError
from core.schemas.contracts import AgentType, ResultMessage, TaskMessage, TaskStatus

_MODULE_HEADER_WITH_PORTS_RE = re.compile(
    r"\bmodule\s+([A-Za-z_]\w*)\s*(?:#\s*\(.*?\)\s*)?\(\s*(.*?)\s*\)\s*;",
    re.DOTALL,
)
_MODULE_HEADER_NO_PORTS_RE = re.compile(r"\bmodule\s+([A-Za-z_]\w*)\s*;", re.DOTALL)


def _read_optional_text(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    return ""


def _sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _short_hash(text: str, n: int = 10) -> str:
    return _sha256_text(text)[:n]


def _parse_attempt(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _stage_dir(kind: str, attempt: int | None) -> str:
    if attempt is None:
        return kind
    return f"{kind}_attempt{attempt}"


def _extract_signature_and_module_name(rtl_text: str, fallback_module: str) -> tuple[str, str]:
    match = _MODULE_HEADER_WITH_PORTS_RE.search(rtl_text)
    if match:
        module_name = match.group(1)
        port_block = " ".join(match.group(2).split())
        return f"module {module_name}({port_block});", module_name
    match = _MODULE_HEADER_NO_PORTS_RE.search(rtl_text)
    if match:
        module_name = match.group(1)
        return f"module {module_name};", module_name
    return f"module {fallback_module}(/* ports unknown */);", fallback_module


def _heuristic_summary(node_id: str, ctx: dict[str, Any], rtl_text: str, tb_text: str) -> str:
    behavior = str(ctx.get("demo_behavior", "") or "").strip()
    verification = ctx.get("verification") if isinstance(ctx.get("verification"), dict) else {}
    goals = verification.get("test_goals") if isinstance(verification.get("test_goals"), list) else []
    module_contract = ctx.get("module_contract") if isinstance(ctx.get("module_contract"), dict) else {}
    style = str(module_contract.get("style", "") or "").strip().lower()
    lowered = rtl_text.lower()
    if style == "integration":
        prefix = f"{node_id} integrates child modules and preserves the defined external contract."
    elif "posedge" in lowered or "always_ff" in lowered:
        prefix = f"{node_id} is a sequential RTL design with explicit clocked behavior."
    elif "assign " in lowered or "always_comb" in lowered:
        prefix = f"{node_id} is a combinational RTL design with direct signal transformation."
    else:
        prefix = f"{node_id} is a passing RTL implementation."
    suffix_parts: list[str] = []
    if behavior:
        suffix_parts.append(behavior[:180].rstrip())
    if goals:
        suffix_parts.append(f"Verification focused on {str(goals[0])[:140].rstrip()}.")
    if tb_text.strip():
        suffix_parts.append("A self-checking testbench passed acceptance and was archived with the design.")
    return " ".join([prefix, *suffix_parts]).strip()


class FinalizerWorker(AgentWorkerBase):
    handled_types = {AgentType.FINALIZE}
    runtime_name = "agent_finalizer"

    def __init__(self, connection_params, stop_event):
        super().__init__(connection_params, stop_event)
        self.gateway = init_llm_gateway("finalizer")

    def handle_task(self, task: TaskMessage) -> ResultMessage:
        ctx = task.context
        if "node_id" not in ctx:
            raise TaskInputError("Missing node_id in task context.")
        if "rtl_path" not in ctx:
            raise TaskInputError("Missing rtl_path in task context.")

        node_id = str(ctx["node_id"])
        attempt = _parse_attempt(ctx.get("attempt"))
        execution_policy = ctx.get("execution_policy") if isinstance(ctx.get("execution_policy"), dict) else {}

        rtl_path = Path(ctx["rtl_path"])
        tb_path = Path(ctx.get("tb_path") or rtl_path.with_name(f"{node_id}_tb.sv"))
        rtl_text = _read_optional_text(rtl_path)
        tb_text = _read_optional_text(tb_path)
        if not rtl_text.strip():
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Finalizer could not read RTL contents from {rtl_path}.",
            )

        signature, module_name = _extract_signature_and_module_name(rtl_text, node_id)
        rtl_sha256 = _sha256_text(rtl_text)
        tb_sha256 = _sha256_text(tb_text)
        archive_root = default_archive_root() / node_id
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle_id = f"{node_id}__{stamp}__attempt{attempt if attempt is not None else 'x'}__{_short_hash(rtl_sha256 + tb_sha256)}"
        bundle_root = archive_root / bundle_id
        logs_root = bundle_root / "logs"
        insights_root = bundle_root / "insights"

        tm_root = task_memory_root() / node_id
        sim_log = _read_optional_text(tm_root / _stage_dir("sim", attempt) / "log.txt")
        lint_log = _read_optional_text(tm_root / _stage_dir("lint", attempt) / "log.txt")
        tb_lint_log = _read_optional_text(tm_root / _stage_dir("tb_lint", attempt) / "log.txt")
        acceptance_log = _read_optional_text(tm_root / _stage_dir("acceptance", attempt) / "log.txt")
        reflection = _read_optional_text(tm_root / _stage_dir("reflect", attempt) / "reflection_insights.json")
        distilled = _read_optional_text(tm_root / _stage_dir("distill", attempt) / "distilled_dataset.json")

        summary = self._generate_summary(
            node_id=node_id,
            ctx=ctx,
            rtl_text=rtl_text,
            tb_text=tb_text,
            reflection_text=reflection,
            acceptance_log=acceptance_log,
        )

        manifest = {
            "schema_version": "1",
            "node_id": node_id,
            "module_name": module_name,
            "run_id": task.run_id,
            "attempt": attempt,
            "signature": signature,
            "summary": summary,
            "rtl_sha256": rtl_sha256,
            "tb_sha256": tb_sha256,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "verification": ctx.get("verification", {}),
            "acceptance": ctx.get("acceptance", {}),
        }

        try:
            logs_root.mkdir(parents=True, exist_ok=True)
            insights_root.mkdir(parents=True, exist_ok=True)
            (bundle_root / "rtl.sv").write_text(rtl_text, encoding="utf-8")
            if tb_text.strip():
                (bundle_root / "tb.sv").write_text(tb_text, encoding="utf-8")
            (bundle_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            (bundle_root / "summary.txt").write_text(summary + "\n", encoding="utf-8")
            if lint_log:
                (logs_root / "lint.log").write_text(lint_log, encoding="utf-8")
            if tb_lint_log:
                (logs_root / "tb_lint.log").write_text(tb_lint_log, encoding="utf-8")
            if sim_log:
                (logs_root / "sim.log").write_text(sim_log, encoding="utf-8")
            if acceptance_log:
                (logs_root / "acceptance.log").write_text(acceptance_log, encoding="utf-8")
            if reflection:
                (insights_root / "reflection_insights.json").write_text(reflection, encoding="utf-8")
            if distilled:
                (insights_root / "distilled_dataset.json").write_text(distilled, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                status=TaskStatus.FAILURE,
                log_output=f"Finalizer could not write archive bundle: {exc}",
            )

        rag_metadata = archive_final_design(
            stage="finalizer",
            record={
                "node_id": node_id,
                "module_name": module_name,
                "run_id": task.run_id or "",
                "attempt": attempt,
                "signature": signature,
                "summary": summary,
                "rtl": rtl_text,
                "rtl_sha256": rtl_sha256,
                "tb_text": tb_text,
                "tb_sha256": tb_sha256,
                "interface_signals": (
                    ctx["interface"]["signals"]
                    if isinstance(ctx.get("interface"), dict) and isinstance(ctx["interface"].get("signals"), list)
                    else []
                ),
                "verification": ctx.get("verification", {}) if isinstance(ctx.get("verification"), dict) else {},
                "tags": ["generated_design", "passing_design", "demo_archive"],
            },
            execution_policy=execution_policy,
        )
        rag_metadata["archive_bundle_id"] = bundle_id

        emit_runtime_event(
            runtime=self.runtime_name,
            event_type="task_completed",
            payload={
                "task_id": str(task.task_id),
                "node_id": node_id,
                "bundle_root": str(bundle_root),
                "rag_used": bool(rag_metadata.get("used")),
            },
        )
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            artifacts_path=str(bundle_root),
            log_output="Finalized the passing design and refreshed reusable design memory.",
            runtime_metadata={"rag": rag_metadata},
        )

    def _generate_summary(
        self,
        *,
        node_id: str,
        ctx: dict[str, Any],
        rtl_text: str,
        tb_text: str,
        reflection_text: str,
        acceptance_log: str,
    ) -> str:
        rag_cfg = get_runtime_config().rag.finalizer
        if not rag_cfg.llm_summary_enabled or not self.gateway or not Message or not MessageRole or not GenerationConfig:
            return _heuristic_summary(node_id, ctx, rtl_text, tb_text)

        rtl_excerpt = rtl_text[: int(rag_cfg.summary_max_rtl_chars)]
        tb_excerpt = tb_text[: int(rag_cfg.summary_max_tb_chars)]
        prompt = render_prompt(
            "finalizer.summary",
            {
                "node_id": node_id,
                "behavior_summary": str(ctx.get("demo_behavior", "") or "").strip(),
                "verification_json": json.dumps(ctx.get("verification", {}), indent=2),
                "acceptance_log": acceptance_log or "No explicit acceptance log.",
                "reflection_text": reflection_text or "None",
                "rtl_excerpt": rtl_excerpt,
                "tb_excerpt": tb_excerpt or "No testbench text provided.",
            },
        )
        llm_cfg = get_runtime_config().llm
        cfg = GenerationConfig(
            temperature=min(0.3, float(llm_cfg.temperature)),
            top_p=llm_cfg.top_p,
            max_tokens=220,
        )
        cfg = apply_reproducibility_settings(cfg, provider=getattr(self.gateway, "provider", None))
        cfg = apply_prompt_output_contract(cfg, prompt)
        trace_dir = task_memory_root() / node_id / _stage_dir("finalize", _parse_attempt(ctx.get("attempt")))
        try:
            write_prompt_trace(prompt, trace_dir)
        except Exception:
            pass
        try:
            resp = asyncio.run(self.gateway.generate(messages=prompt.messages, config=cfg))  # type: ignore[arg-type]
        except Exception:
            return _heuristic_summary(node_id, ctx, rtl_text, tb_text)

        try:
            get_tracker().log_llm_call(
                agent=self.runtime_name,
                node_id=node_id,
                model=getattr(resp, "model_name", "unknown"),
                provider=getattr(resp, "provider", "unknown"),
                prompt_tokens=getattr(resp, "input_tokens", 0),
                completion_tokens=getattr(resp, "output_tokens", 0),
                total_tokens=getattr(resp, "total_tokens", 0),
                estimated_cost_usd=getattr(resp, "estimated_cost_usd", None),
                metadata=build_prompt_metadata(prompt, extra={"stage": "finalizer_summary"}),
            )
        except Exception:
            pass

        text = str(getattr(resp, "content", "") or "").strip()
        return text or _heuristic_summary(node_id, ctx, rtl_text, tb_text)
