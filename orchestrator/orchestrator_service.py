"""
Minimal orchestrator for the demo. Loads DAG and Design Context, publishes
tasks to RabbitMQ queues, consumes results, and advances a simple state machine:
Implementation -> Lint -> Testbench -> TB Lint -> Simulation -> Acceptance -> Done (on pass).
On simulation failure, it runs Distill -> Reflect -> Debug (code patch) and retries verification.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict

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

from orchestrator.context_builder import DemoContextBuilder
from orchestrator.state_machine import Node, NodeState
from orchestrator.task_memory import TaskMemory

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


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
    ):
        self.connection_params = connection_params
        self.design_context_path = design_context_path
        self.dag_path = dag_path
        self.rtl_root = rtl_root
        self.context_builder = DemoContextBuilder(design_context_path, rtl_root)
        self._design_context = json.loads(design_context_path.read_text())
        self._node_scopes = {
            node_id: node.get("verification_scope", "full")
            for node_id, node in self._design_context.get("nodes", {}).items()
        }
        self._top_module = self._design_context.get("top_module")
        self.dag = json.loads(dag_path.read_text())
        self.nodes: Dict[str, Node] = {n["id"]: Node(n["id"]) for n in self.dag["nodes"]}
        self.deps_map: Dict[str, set[str]] = {
            n["id"]: set(n.get("deps", []) or []) for n in self.dag["nodes"]
        }
        self.task_memory = TaskMemory(task_memory_root)
        self.state_callback = state_callback

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
        task = TaskMessage(entity_type=entity, task_type=task_type, context=ctx)
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
        print(f"{node_id} -> {new_state.value}")
        emit_runtime_event(runtime="orchestrator", event_type="state_transition", payload={"node_id": node_id, "state": new_state.value})
        if self.state_callback:
            self.state_callback(node_id, new_state.value)

    def run(self, timeout_s: float = 30.0) -> None:
        if timeout_s <= 0:
            timeout_s = float("inf")
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.queue_declare(queue="results", durable=True)
            ch.queue_bind(queue="results", exchange=TASK_EXCHANGE, routing_key=RESULTS_ROUTING_KEY)

            node_ids = list(self.nodes.keys())
            tasks: Dict[str, Dict[str, TaskMessage]] = {}
            pending_nodes = set(node_ids)
            active_nodes = set()
            done_nodes = set()
            max_debug_retries = int(os.getenv("DEBUG_MAX_RETRIES", "2"))
            attempt_by_node: dict[str, int] = {}
            debug_attempts_by_node: dict[str, dict[str, int]] = {}
            tb_generated_by_node: dict[str, bool] = {}
            post_lint_next_kind: dict[str, str] = {}
            pending_debug: dict[str, dict[str, Any]] = {}
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
                self._advance(node_id, NodeState.IMPLEMENTING)
                impl_task = self._publish_task(ch, EntityType.REASONING, AgentType.IMPLEMENTATION, node_id)
                tasks[node_id] = {"impl": impl_task}
                pending_nodes.discard(node_id)
                active_nodes.add(node_id)

            def start_ready_nodes() -> None:
                ready = [n for n in pending_nodes if self.deps_map.get(n, set()) <= done_nodes]
                for node_id in ready:
                    start_node(node_id)

            def fail_dependents(failed_node: str) -> None:
                blocked = [n for n in list(pending_nodes) if failed_node in self.deps_map.get(n, set())]
                for node_id in blocked:
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
                start_ready_nodes()

            start_ready_nodes()
            if not active_nodes and pending_nodes:
                raise RuntimeError("No DAG roots available to start. Check dependency graph for cycles or missing nodes.")

            start = time.time()

            while time.time() - start < timeout_s and len(done_nodes) < len(node_ids):
                method, props, body = ch.basic_get(queue="results", auto_ack=True)
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
                    continue

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

                if result.status is not TaskStatus.SUCCESS:
                    _snapshot_failure_sources(target_node, stage, kind=kind)
                _mirror_stage_to_observability(target_node, stage)

                print(f"Result for {target_node} stage {stage}: {result.status.value}")

                if result.status is not TaskStatus.SUCCESS:
                    if kind == "lint":
                        reason = "rtl_lint"
                        attempt = stage_attempt or attempt_by_node.get(target_node, 1)
                        if _get_debug_attempts(target_node, reason) >= max_debug_retries:
                            print(f"{target_node} debug retries exhausted for {reason} ({max_debug_retries}); failing.")
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
                        debug = self._publish_task(
                            ch,
                            EntityType.REASONING,
                            AgentType.DEBUG,
                            target_node,
                            attempt=attempt,
                            extra_ctx={"debug_reason": reason},
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
                            print(f"{target_node} debug retries exhausted for {reason} ({max_debug_retries}); failing.")
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
                        debug = self._publish_task(
                            ch,
                            EntityType.REASONING,
                            AgentType.DEBUG,
                            target_node,
                            attempt=attempt,
                            extra_ctx={"debug_reason": reason},
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
                    if self._node_scopes.get(target_node, "full") != "full":
                        print(f"Skipping TB/SIM for {target_node} (non-top module).")
                        _finish_done(target_node)
                        continue
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
                    reflect = self._publish_task(
                        ch,
                        EntityType.REASONING,
                        AgentType.REFLECTION,
                        target_node,
                        attempt=attempt,
                    )
                    tasks[target_node][reflect_key] = reflect
                elif kind == "reflect":
                    attempt = stage_attempt
                    if attempt is None:
                        _finish_failed(target_node)
                        continue
                    reason = "sim"
                    if _get_debug_attempts(target_node, reason) >= max_debug_retries:
                        print(f"{target_node} debug retries exhausted for {reason} ({max_debug_retries}); failing.")
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
                    debug = self._publish_task(
                        ch,
                        EntityType.REASONING,
                        AgentType.DEBUG,
                        target_node,
                        attempt=attempt,
                        extra_ctx={"debug_reason": reason},
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
                        print(f"{target_node} debug produced no code changes; failing.")
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
                print("Demo timed out before all nodes completed.")
