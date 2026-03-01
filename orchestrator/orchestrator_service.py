"""
Minimal orchestrator for the demo. Loads DAG and Design Context, publishes
tasks to RabbitMQ queues, consumes results, and advances a simple state machine:
Implementation -> Lint -> Testbench -> TB Lint -> Simulation -> Acceptance -> Done (on pass).
On simulation failure, it runs Distill -> Reflect -> Debug (code patch) and retries verification.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pika
from core.schemas.contracts import (
    AgentType,
    EntityType,
    ResultMessage,
    TaskMessage,
    TaskStatus,
    WorkerType,
)
from core.observability.emitter import emit_runtime_event
from core.observability.run_artifacts import get_run_artifacts_dir, mirror_directory
from core.runtime.broker import (
    DEFAULT_RESULTS_ROUTING_KEY,
    TASK_EXCHANGE,
    declare_results_queue,
)
from core.runtime.config import get_runtime_config

from orchestrator.context_builder import DemoContextBuilder
from orchestrator.state_machine import Node, NodeState
from orchestrator.task_memory import TaskMemory


class DemoOrchestrator:
    """
    Drives a richer state machine:
        PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> TB_LINTING -> SIMULATING -> ACCEPTING -> DONE (on pass)
        SIMULATING (fail) -> DISTILLING -> REFLECTING -> DEBUGGING -> (re-run verification, bounded retries)
        LINTING/TB_LINTING (fail) -> DEBUGGING -> (re-run verification, bounded retries)
        ACCEPTING (fail) -> FAILED
    Persists logs/artifact paths to Task Memory. Testbench stage builds TB before TB lint and simulation.
    """

    def __init__(
        self,
        connection_params: pika.ConnectionParameters,
        design_context_path: Path,
        dag_path: Path,
        rtl_root: Path,
        task_memory_root: Path,
        state_callback=None,
        event_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
        raw_progress: bool = True,
        *,
        run_id: str | None = None,
        results_routing_key: str = DEFAULT_RESULTS_ROUTING_KEY,
        results_queue_name: str | None = None,
        allow_repair_loop: bool = True,
        execution_policy: Optional[dict[str, Any]] = None,
    ):
        self.connection_params = connection_params
        self.design_context_path = design_context_path
        self.dag_path = dag_path
        self.rtl_root = rtl_root
        self.context_builder = DemoContextBuilder(design_context_path, rtl_root)
        self._design_context = json.loads(design_context_path.read_text())
        self._top_module = self._design_context.get("top_module")
        self.dag = json.loads(dag_path.read_text())
        self.nodes: Dict[str, Node] = {n["id"]: Node(n["id"]) for n in self.dag["nodes"]}
        self.deps_map: Dict[str, set[str]] = {
            n["id"]: set(n.get("deps", []) or []) for n in self.dag["nodes"]
        }
        self.task_memory = TaskMemory(task_memory_root)
        self.state_callback = state_callback
        self.event_callback = event_callback
        self.raw_progress = raw_progress
        self.run_id = run_id
        self.results_routing_key = results_routing_key
        self.results_queue_name = results_queue_name
        self.allow_repair_loop = allow_repair_loop
        self.execution_policy = execution_policy or {}

    def _emit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.event_callback:
            return
        try:
            self.event_callback(event_type, payload)
        except Exception:
            return

    def _emit_progress(self, message: str, *, event_type: str | None = None, payload: dict[str, Any] | None = None) -> None:
        if self.raw_progress:
            print(message)
        if event_type:
            self._emit_event(event_type, payload or {})

    def _publish_task(
        self,
        ch: pika.adapters.blocking_connection.BlockingChannel,
        entity: EntityType,
        task_type: Any,
        node_id: str,
        *,
        attempt: int | None = None,
        extra_ctx: dict[str, Any] | None = None,
    ) -> TaskMessage:
        ctx = self.context_builder.build(node_id)
        if attempt is not None:
            ctx["attempt"] = attempt
        if extra_ctx:
            ctx.update(extra_ctx)
        if self.execution_policy:
            ctx.setdefault("execution_policy", self.execution_policy)
        task = TaskMessage(
            entity_type=entity,
            task_type=task_type,
            context=ctx,
            run_id=self.run_id,
            results_routing_key=self.results_routing_key,
        )
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=entity.value,
            body=task.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
        emit_runtime_event(
            runtime="orchestrator",
            event_type="task_published",
            payload={"node_id": node_id, "task_id": str(task.task_id), "entity": entity.value, "task_type": task_type.value},
        )
        return task

    def _advance(self, node_id: str, new_state: NodeState) -> None:
        node = self.nodes[node_id]
        node.transition(new_state)
        self._emit_progress(
            f"{node_id} -> {new_state.value}",
            event_type="state_transition",
            payload={"node_id": node_id, "state": new_state.value},
        )
        emit_runtime_event(runtime="orchestrator", event_type="state_transition", payload={"node_id": node_id, "state": new_state.value})
        if self.state_callback:
            self.state_callback(node_id, new_state.value)

    def run(self, timeout_s: float = 30.0) -> None:
        if timeout_s <= 0:
            timeout_s = float("inf")
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            results_queue = declare_results_queue(
                ch,
                results_routing_key=self.results_routing_key,
                queue_name=self.results_queue_name,
            )

            node_ids = list(self.nodes.keys())
            tasks: Dict[str, Dict[str, TaskMessage]] = {}
            pending_nodes = set(node_ids)
            active_nodes = set()
            done_nodes = set()
            succeeded_nodes = set()
            configured_retries = int(get_runtime_config().debug.max_retries)
            max_debug_retries = int(
                self.execution_policy.get("debug_max_retries", configured_retries)
            )
            attempt_by_node: dict[str, int] = {}
            debug_attempts_by_node: dict[str, dict[str, int]] = {}
            tb_generated_by_node: dict[str, bool] = {}
            post_lint_next_kind: dict[str, str] = {}
            pending_debug: dict[str, dict[str, Any]] = {}
            attempt_history_by_node: dict[str, dict[int, dict[str, Any]]] = {}
            obs_run_dir = get_run_artifacts_dir()

            def _dump_model(payload: Any) -> Any:
                if payload is None:
                    return None
                if hasattr(payload, "model_dump"):
                    return payload.model_dump(mode="json")
                if hasattr(payload, "dict"):
                    return payload.dict()
                return payload

            def _maybe_json(text: str) -> Any:
                try:
                    return json.loads(text)
                except Exception:
                    return text

            def _stage_key(kind: str, attempt: int | None = None) -> str:
                if attempt is None:
                    return kind
                return f"{kind}_attempt{attempt}"

            def _parse_stage_key(stage_key: str) -> tuple[str, int | None]:
                if "_attempt" not in stage_key:
                    return stage_key, None
                kind, _, suffix = stage_key.partition("_attempt")
                if suffix.isdigit():
                    return kind, int(suffix)
                return kind, None

            def _short_log_excerpt(text: str, limit: int = 280) -> str:
                stripped = (text or "").strip()
                if len(stripped) <= limit:
                    return stripped
                return stripped[:limit].rstrip() + " ..."

            def _extract_fail_line(text: str) -> str | None:
                for raw in (text or "").splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    upper = line.upper()
                    if "FAIL" in upper or "ERROR" in upper:
                        return line
                return None

            def _normalize_failure_line(line: str) -> str:
                norm = line.lower()
                norm = re.sub(r"\bcycle\s*=\s*\d+", "cycle=?", norm)
                norm = re.sub(r"\btime\s*=\s*\d+", "time=?", norm)
                norm = re.sub(r"\battempt\s*=\s*\d+", "attempt=?", norm)
                norm = re.sub(r"\d+", "?", norm)
                norm = re.sub(r"\s+", " ", norm).strip()
                return norm

            def _failure_signature(kind: str, log_output: str) -> str | None:
                fail_line = _extract_fail_line(log_output)
                if not fail_line:
                    return None
                normalized = _normalize_failure_line(fail_line)
                digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
                return f"{kind}:{digest}"

            def _attempt_entry(node_id: str, attempt: int) -> dict[str, Any]:
                history = attempt_history_by_node.setdefault(node_id, {})
                if attempt in history:
                    return history[attempt]
                entry = {
                    "attempt": attempt,
                    "outcome": "in_progress",
                    "failure_signature": None,
                    "failure_line": None,
                    "touched_files": [],
                    "artifact_hashes": {},
                    "patch_summary": None,
                    "status_by_stage": {},
                    "latest_stage": None,
                    "last_log_excerpt": "",
                }
                history[attempt] = entry
                return entry

            def _record_attempt_history(
                *,
                node_id: str,
                kind: str,
                stage_attempt: int | None,
                result: ResultMessage,
            ) -> None:
                attempt = stage_attempt or attempt_by_node.get(node_id, 1)
                entry = _attempt_entry(node_id, attempt)
                status_text = result.status.value.lower()
                entry["status_by_stage"][kind] = status_text
                entry["latest_stage"] = kind
                entry["last_log_excerpt"] = _short_log_excerpt(result.log_output or "")

                if result.status is not TaskStatus.SUCCESS:
                    entry["outcome"] = f"{kind}_failed"
                elif kind == "sim":
                    entry["outcome"] = "sim_passed"
                elif kind == "acceptance":
                    entry["outcome"] = "accepted"

                if kind == "sim" and result.status is not TaskStatus.SUCCESS:
                    signature = _failure_signature(kind, result.log_output or "")
                    fail_line = _extract_fail_line(result.log_output or "")
                    entry["failure_signature"] = signature
                    entry["failure_line"] = fail_line
                    entry["outcome"] = "sim_failed"

                if kind == "debug":
                    parsed = _maybe_json(result.reflections or "")
                    if isinstance(parsed, dict):
                        touched = parsed.get("touched_files")
                        if isinstance(touched, list):
                            entry["touched_files"] = [str(item) for item in touched if str(item).strip()]
                        summary = parsed.get("summary")
                        if isinstance(summary, str) and summary.strip():
                            entry["patch_summary"] = summary.strip()
                        hashes: dict[str, Any] = {}
                        rtl_sha = parsed.get("rtl_sha256")
                        tb_sha = parsed.get("tb_sha256")
                        if isinstance(rtl_sha, str) and rtl_sha:
                            hashes["rtl_sha256"] = rtl_sha
                        if isinstance(tb_sha, str) and tb_sha:
                            hashes["tb_sha256"] = tb_sha
                        if hashes:
                            entry["artifact_hashes"] = hashes
                        if result.status is TaskStatus.SUCCESS:
                            entry["outcome"] = "debug_patched"

            def _attempt_history_context(node_id: str, attempt: int | None, max_items: int = 3) -> list[dict[str, Any]]:
                by_attempt = attempt_history_by_node.get(node_id, {})
                if not by_attempt:
                    return []
                attempt_cap = attempt if attempt is not None else max(by_attempt.keys())
                selected_attempts = [a for a in sorted(by_attempt.keys()) if a <= attempt_cap]
                selected_attempts = selected_attempts[-max_items:]
                payload: list[dict[str, Any]] = []
                for idx in selected_attempts:
                    item = by_attempt.get(idx, {})
                    payload.append(
                        {
                            "attempt": idx,
                            "outcome": item.get("outcome"),
                            "failure_signature": item.get("failure_signature"),
                            "failure_line": item.get("failure_line"),
                            "touched_files": item.get("touched_files", []),
                            "artifact_hashes": item.get("artifact_hashes", {}),
                            "patch_summary": item.get("patch_summary"),
                            "status_by_stage": item.get("status_by_stage", {}),
                        }
                    )
                return payload

            def _stagnation_context(node_id: str, attempt: int | None) -> dict[str, Any]:
                by_attempt = attempt_history_by_node.get(node_id, {})
                if not by_attempt:
                    return {"stuck": False}
                attempt_cap = attempt if attempt is not None else max(by_attempt.keys())
                signatures: list[tuple[int, str]] = []
                for idx in sorted(by_attempt.keys()):
                    if idx > attempt_cap:
                        continue
                    sig = by_attempt[idx].get("failure_signature")
                    if isinstance(sig, str) and sig:
                        signatures.append((idx, sig))
                if len(signatures) < 2:
                    return {"stuck": False}
                last_attempt, last_sig = signatures[-1]
                repeat = 1
                repeated_attempts = [last_attempt]
                for idx, sig in reversed(signatures[:-1]):
                    if sig != last_sig:
                        break
                    repeat += 1
                    repeated_attempts.append(idx)
                repeated_attempts.reverse()
                stuck = repeat >= 2
                if not stuck:
                    return {
                        "stuck": False,
                        "current_failure_signature": last_sig,
                        "stuck_repeated_failures": repeat,
                    }
                reason = (
                    f"Repeated failure signature {last_sig} across attempts "
                    f"{','.join(str(v) for v in repeated_attempts)}."
                )
                return {
                    "stuck": True,
                    "stuck_reason": reason,
                    "current_failure_signature": last_sig,
                    "stuck_repeated_failures": repeat,
                    "stuck_attempts": repeated_attempts,
                }

            def _hash_file(path: Path) -> str:
                if not path.exists():
                    return ""
                return hashlib.sha256(path.read_bytes()).hexdigest()

            def _get_debug_attempts(node_id: str, reason: str) -> int:
                return debug_attempts_by_node.get(node_id, {}).get(reason, 0)

            def _inc_debug_attempts(node_id: str, reason: str) -> int:
                debug_attempts_by_node.setdefault(node_id, {})
                debug_attempts_by_node[node_id][reason] = _get_debug_attempts(node_id, reason) + 1
                return debug_attempts_by_node[node_id][reason]

            def _reset_debug_attempts(node_id: str, reason: str) -> None:
                debug_attempts_by_node.setdefault(node_id, {})
                debug_attempts_by_node[node_id][reason] = 0

            def _snapshot_failure_sources(node_id: str, stage_key: str, *, kind: str) -> None:
                if kind not in ("lint", "tb_lint", "sim", "debug"):
                    return
                try:
                    ctx = self.context_builder.build(node_id)
                    rtl_path = Path(ctx["rtl_path"])
                    rtl_paths = ctx.get("rtl_paths") or [ctx["rtl_path"]]
                    tb_path = Path(ctx.get("tb_path") or rtl_path.with_name(f"{node_id}_tb.sv"))
                    stage_dir = self.task_memory.root / node_id / stage_key
                    stage_dir.mkdir(parents=True, exist_ok=True)
                    for rtl_entry in rtl_paths:
                        rtl_path = Path(rtl_entry)
                        if rtl_path.exists():
                            shutil.copy2(rtl_path, stage_dir / rtl_path.name)
                    if kind in ("tb_lint", "sim", "debug") and tb_path.exists():
                        shutil.copy2(tb_path, stage_dir / tb_path.name)
                except Exception:
                    return

            def _mirror_stage_to_observability(node_id: str, stage_key: str) -> None:
                try:
                    src = self.task_memory.root / node_id / stage_key
                    dst = obs_run_dir / "task_memory" / node_id / stage_key
                    mirror_directory(src, dst)
                    emit_runtime_event(
                        runtime="orchestrator",
                        event_type="task_memory_mirrored",
                        payload={"node_id": node_id, "stage": stage_key, "path": str(dst)},
                    )
                except Exception:
                    return

            def start_node(node_id: str) -> None:
                attempt_by_node[node_id] = 1
                debug_attempts_by_node[node_id] = {}
                tb_generated_by_node[node_id] = False
                attempt_history_by_node[node_id] = {}
                self._advance(node_id, NodeState.IMPLEMENTING)
                impl_task = self._publish_task(ch, EntityType.REASONING, AgentType.IMPLEMENTATION, node_id)
                tasks[node_id] = {"impl": impl_task}
                pending_nodes.discard(node_id)
                active_nodes.add(node_id)

            def start_ready_nodes() -> None:
                # A node is ready only when all dependencies have succeeded (DONE), not merely terminated.
                ready = [n for n in pending_nodes if self.deps_map.get(n, set()) <= succeeded_nodes]
                for node_id in ready:
                    start_node(node_id)

            def fail_dependents(failed_node: str) -> None:
                # Propagate failure through the transitive dependent closure.
                failed_closure = {failed_node}
                blocked: set[str] = set()
                changed = True
                while changed:
                    changed = False
                    for node_id in list(pending_nodes):
                        if node_id in blocked:
                            continue
                        deps = self.deps_map.get(node_id, set())
                        if deps & failed_closure:
                            blocked.add(node_id)
                            failed_closure.add(node_id)
                            changed = True

                for node_id in sorted(blocked):
                    self._advance(node_id, NodeState.FAILED)
                    pending_nodes.discard(node_id)
                    done_nodes.add(node_id)

            def _finish_failed(node_id: str) -> None:
                self._advance(node_id, NodeState.FAILED)
                active_nodes.discard(node_id)
                done_nodes.add(node_id)
                fail_dependents(node_id)
                start_ready_nodes()

            def _finish_done(node_id: str) -> None:
                self._advance(node_id, NodeState.DONE)
                active_nodes.discard(node_id)
                done_nodes.add(node_id)
                succeeded_nodes.add(node_id)
                start_ready_nodes()

            start_ready_nodes()
            if not active_nodes and pending_nodes:
                raise RuntimeError("No DAG roots available to start. Check dependency graph for cycles or missing nodes.")

            start = time.time()

            while time.time() - start < timeout_s and len(done_nodes) < len(node_ids):
                method, props, body = ch.basic_get(queue=results_queue, auto_ack=False)
                if body is None:
                    time.sleep(0.1)
                    continue
                result = ResultMessage.model_validate_json(body)
                target_node = None
                stage = None
                for node_id, bundle in tasks.items():
                    for key, t in bundle.items():
                        if t.task_id == result.task_id:
                            target_node = node_id
                            stage = key
                            break
                    if target_node:
                        break
                if not target_node:
                    ch.basic_nack(method.delivery_tag, requeue=True)
                    continue
                ch.basic_ack(method.delivery_tag)

                kind, stage_attempt = _parse_stage_key(stage)
                self.task_memory.record_log(target_node, stage, result.log_output)
                if result.artifacts_path:
                    self.task_memory.record_artifact_path(target_node, stage, result.artifacts_path)
                if result.reflection_insights:
                    self.task_memory.record_json(
                        target_node,
                        stage,
                        "reflection_insights.json",
                        _dump_model(result.reflection_insights),
                    )
                if result.reflections:
                    self.task_memory.record_json(target_node, stage, "reflections.json", _maybe_json(result.reflections))
                _record_attempt_history(node_id=target_node, kind=kind, stage_attempt=stage_attempt, result=result)

                if result.status is not TaskStatus.SUCCESS:
                    _snapshot_failure_sources(target_node, stage, kind=kind)
                _mirror_stage_to_observability(target_node, stage)

                self._emit_progress(
                    f"Result for {target_node} stage {stage}: {result.status.value}",
                    event_type="stage_result",
                    payload={
                        "node_id": target_node,
                        "stage_key": stage,
                        "stage_kind": kind,
                        "attempt": stage_attempt,
                        "status": result.status.value,
                        "log_output": result.log_output,
                        "artifacts_path": result.artifacts_path,
                        "reflections": result.reflections,
                        "reflection_insights": _dump_model(result.reflection_insights),
                    },
                )

                if result.status is not TaskStatus.SUCCESS:
                    if not self.allow_repair_loop and kind in {"lint", "tb_lint", "sim", "distill", "reflect", "debug"}:
                        _finish_failed(target_node)
                        continue
                    if kind == "lint":
                        reason = "rtl_lint"
                        attempt = stage_attempt or attempt_by_node.get(target_node, 1)
                        if _get_debug_attempts(target_node, reason) >= max_debug_retries:
                            self._emit_progress(
                                f"{target_node} debug retries exhausted for {reason} ({max_debug_retries}); failing.",
                                event_type="execution_note",
                                payload={"node_id": target_node, "reason": reason, "attempt": attempt, "max_debug_retries": max_debug_retries},
                            )
                            _finish_failed(target_node)
                            continue
                        ctx = self.context_builder.build(target_node)
                        rtl_path = Path(ctx["rtl_path"])
                        tb_path = Path(ctx.get("tb_path") or rtl_path.with_name(f"{target_node}_tb.sv"))
                        pending_debug[target_node] = {
                            "rtl_sha": _hash_file(rtl_path),
                            "tb_sha": _hash_file(tb_path),
                            "from_attempt": attempt,
                            "reason": reason,
                        }
                        _inc_debug_attempts(target_node, reason)
                        self._advance(target_node, NodeState.DEBUGGING)
                        debug_key = _stage_key("debug", attempt)
                        debug_extra_ctx = {
                            "debug_reason": reason,
                            "attempt_history": _attempt_history_context(target_node, attempt),
                        }
                        debug_extra_ctx.update(_stagnation_context(target_node, attempt))
                        debug = self._publish_task(
                            ch,
                            EntityType.REASONING,
                            AgentType.DEBUG,
                            target_node,
                            attempt=attempt,
                            extra_ctx=debug_extra_ctx,
                        )
                        tasks[target_node][debug_key] = debug
                        continue

                    if kind == "sim":
                        if stage_attempt is None:
                            _finish_failed(target_node)
                            continue
                        self._advance(target_node, NodeState.DISTILLING)
                        distill_key = _stage_key("distill", stage_attempt)
                        distill = self._publish_task(
                            ch,
                            EntityType.LIGHT_DETERMINISTIC,
                            WorkerType.DISTILLATION,
                            target_node,
                            attempt=stage_attempt,
                        )
                        tasks[target_node][distill_key] = distill
                        continue

                    if kind == "tb_lint":
                        reason = "tb_lint"
                        attempt = stage_attempt or attempt_by_node.get(target_node, 1)
                        if _get_debug_attempts(target_node, reason) >= max_debug_retries:
                            self._emit_progress(
                                f"{target_node} debug retries exhausted for {reason} ({max_debug_retries}); failing.",
                                event_type="execution_note",
                                payload={"node_id": target_node, "reason": reason, "attempt": attempt, "max_debug_retries": max_debug_retries},
                            )
                            _finish_failed(target_node)
                            continue
                        ctx = self.context_builder.build(target_node)
                        rtl_path = Path(ctx["rtl_path"])
                        tb_path = Path(ctx.get("tb_path") or rtl_path.with_name(f"{target_node}_tb.sv"))
                        pending_debug[target_node] = {
                            "rtl_sha": _hash_file(rtl_path),
                            "tb_sha": _hash_file(tb_path),
                            "from_attempt": attempt,
                            "reason": reason,
                        }
                        _inc_debug_attempts(target_node, reason)
                        self._advance(target_node, NodeState.DEBUGGING)
                        debug_key = _stage_key("debug", attempt)
                        debug_extra_ctx = {
                            "debug_reason": reason,
                            "attempt_history": _attempt_history_context(target_node, attempt),
                        }
                        debug_extra_ctx.update(_stagnation_context(target_node, attempt))
                        debug = self._publish_task(
                            ch,
                            EntityType.REASONING,
                            AgentType.DEBUG,
                            target_node,
                            attempt=attempt,
                            extra_ctx=debug_extra_ctx,
                        )
                        tasks[target_node][debug_key] = debug
                        continue

                    _finish_failed(target_node)
                    continue

                # SUCCESS path
                if kind == "impl":
                    attempt = attempt_by_node.get(target_node, 1)
                    self._advance(target_node, NodeState.LINTING)
                    lint_key = _stage_key("lint", attempt)
                    lint_task = self._publish_task(
                        ch,
                        EntityType.LIGHT_DETERMINISTIC,
                        WorkerType.LINTER,
                        target_node,
                        attempt=attempt,
                    )
                    tasks[target_node][lint_key] = lint_task
                elif kind == "lint":
                    _reset_debug_attempts(target_node, "rtl_lint")
                    if not tb_generated_by_node.get(target_node, False):
                        self._advance(target_node, NodeState.TESTBENCHING)
                        tb_task = self._publish_task(ch, EntityType.REASONING, AgentType.TESTBENCH, target_node)
                        tasks[target_node]["tb"] = tb_task
                        continue
                    # Retry lint: decide whether to run TB lint or go straight to sim.
                    next_kind = post_lint_next_kind.pop(target_node, "sim")
                    attempt = stage_attempt or attempt_by_node.get(target_node, 1)
                    if next_kind == "tb_lint":
                        self._advance(target_node, NodeState.TB_LINTING)
                        tb_lint_key = _stage_key("tb_lint", attempt)
                        tb_lint_task = self._publish_task(
                            ch,
                            EntityType.LIGHT_DETERMINISTIC,
                            WorkerType.TESTBENCH_LINTER,
                            target_node,
                            attempt=attempt,
                        )
                        tasks[target_node][tb_lint_key] = tb_lint_task
                    else:
                        self._advance(target_node, NodeState.SIMULATING)
                        sim_key = _stage_key("sim", attempt)
                        sim_task = self._publish_task(
                            ch,
                            EntityType.HEAVY_DETERMINISTIC,
                            WorkerType.SIMULATOR,
                            target_node,
                            attempt=attempt,
                        )
                        tasks[target_node][sim_key] = sim_task
                elif kind == "tb":
                    tb_generated_by_node[target_node] = True
                    attempt = attempt_by_node.get(target_node, 1)
                    self._advance(target_node, NodeState.TB_LINTING)
                    tb_lint_key = _stage_key("tb_lint", attempt)
                    tb_lint_task = self._publish_task(
                        ch,
                        EntityType.LIGHT_DETERMINISTIC,
                        WorkerType.TESTBENCH_LINTER,
                        target_node,
                        attempt=attempt,
                    )
                    tasks[target_node][tb_lint_key] = tb_lint_task
                elif kind == "tb_lint":
                    _reset_debug_attempts(target_node, "tb_lint")
                    attempt = stage_attempt or attempt_by_node.get(target_node, 1)
                    self._advance(target_node, NodeState.SIMULATING)
                    sim_key = _stage_key("sim", attempt)
                    sim_task = self._publish_task(
                        ch,
                        EntityType.HEAVY_DETERMINISTIC,
                        WorkerType.SIMULATOR,
                        target_node,
                        attempt=attempt,
                    )
                    tasks[target_node][sim_key] = sim_task
                elif kind == "sim":
                    _reset_debug_attempts(target_node, "sim")
                    attempt = stage_attempt or attempt_by_node.get(target_node, 1)
                    self._advance(target_node, NodeState.ACCEPTING)
                    accept_key = _stage_key("acceptance", attempt)
                    accept_task = self._publish_task(
                        ch,
                        EntityType.LIGHT_DETERMINISTIC,
                        WorkerType.ACCEPTANCE,
                        target_node,
                        attempt=attempt,
                    )
                    tasks[target_node][accept_key] = accept_task
                elif kind == "acceptance":
                    _finish_done(target_node)
                elif kind == "distill":
                    attempt = stage_attempt
                    if attempt is None:
                        _finish_failed(target_node)
                        continue
                    self._advance(target_node, NodeState.REFLECTING)
                    reflect_key = _stage_key("reflect", attempt)
                    reflect_extra_ctx = {"attempt_history": _attempt_history_context(target_node, attempt)}
                    reflect_extra_ctx.update(_stagnation_context(target_node, attempt))
                    reflect = self._publish_task(
                        ch,
                        EntityType.REASONING,
                        AgentType.REFLECTION,
                        target_node,
                        attempt=attempt,
                        extra_ctx=reflect_extra_ctx,
                    )
                    tasks[target_node][reflect_key] = reflect
                elif kind == "reflect":
                    attempt = stage_attempt
                    if attempt is None:
                        _finish_failed(target_node)
                        continue
                    reason = "sim"
                    if _get_debug_attempts(target_node, reason) >= max_debug_retries:
                        self._emit_progress(
                            f"{target_node} debug retries exhausted for {reason} ({max_debug_retries}); failing.",
                            event_type="execution_note",
                            payload={"node_id": target_node, "reason": reason, "attempt": attempt, "max_debug_retries": max_debug_retries},
                        )
                        _finish_failed(target_node)
                        continue
                    ctx = self.context_builder.build(target_node)
                    rtl_path = Path(ctx["rtl_path"])
                    tb_path = Path(ctx.get("tb_path") or rtl_path.with_name(f"{target_node}_tb.sv"))
                    pending_debug[target_node] = {
                        "rtl_sha": _hash_file(rtl_path),
                        "tb_sha": _hash_file(tb_path),
                        "from_attempt": attempt,
                        "reason": reason,
                    }
                    _inc_debug_attempts(target_node, reason)
                    self._advance(target_node, NodeState.DEBUGGING)
                    debug_key = _stage_key("debug", attempt)
                    debug_extra_ctx = {
                        "debug_reason": reason,
                        "attempt_history": _attempt_history_context(target_node, attempt),
                    }
                    debug_extra_ctx.update(_stagnation_context(target_node, attempt))
                    debug = self._publish_task(
                        ch,
                        EntityType.REASONING,
                        AgentType.DEBUG,
                        target_node,
                        attempt=attempt,
                        extra_ctx=debug_extra_ctx,
                    )
                    tasks[target_node][debug_key] = debug
                elif kind == "debug":
                    meta = pending_debug.pop(target_node, None)
                    if not meta:
                        _finish_failed(target_node)
                        continue
                    ctx = self.context_builder.build(target_node)
                    rtl_path = Path(ctx["rtl_path"])
                    tb_path = Path(ctx.get("tb_path") or rtl_path.with_name(f"{target_node}_tb.sv"))
                    rtl_changed = meta.get("rtl_sha", "") != _hash_file(rtl_path)
                    tb_changed = meta.get("tb_sha", "") != _hash_file(tb_path)
                    from_attempt = int(meta.get("from_attempt", attempt_by_node.get(target_node, 1)))
                    next_attempt = from_attempt + 1
                    attempt_by_node[target_node] = next_attempt

                    if not rtl_changed and not tb_changed:
                        self._emit_progress(
                            f"{target_node} debug produced no code changes; failing.",
                            event_type="execution_note",
                            payload={"node_id": target_node, "reason": "no_code_changes", "attempt": from_attempt},
                        )
                        _finish_failed(target_node)
                        continue

                    if rtl_changed:
                        self._advance(target_node, NodeState.LINTING)
                        lint_key = _stage_key("lint", next_attempt)
                        post_lint_next_kind[target_node] = "tb_lint" if tb_changed else "sim"
                        lint_task = self._publish_task(
                            ch,
                            EntityType.LIGHT_DETERMINISTIC,
                            WorkerType.LINTER,
                            target_node,
                            attempt=next_attempt,
                        )
                        tasks[target_node][lint_key] = lint_task
                    elif tb_changed:
                        self._advance(target_node, NodeState.TB_LINTING)
                        tb_lint_key = _stage_key("tb_lint", next_attempt)
                        tb_lint_task = self._publish_task(
                            ch,
                            EntityType.LIGHT_DETERMINISTIC,
                            WorkerType.TESTBENCH_LINTER,
                            target_node,
                            attempt=next_attempt,
                        )
                        tasks[target_node][tb_lint_key] = tb_lint_task

            if len(done_nodes) < len(node_ids):
                self._emit_progress(
                    "Demo timed out before all nodes completed.",
                    event_type="execution_note",
                    payload={"reason": "timeout", "done_nodes": len(done_nodes), "total_nodes": len(node_ids)},
                )
