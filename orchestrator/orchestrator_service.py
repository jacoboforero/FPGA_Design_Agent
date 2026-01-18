"""
Minimal orchestrator for the demo. Loads DAG and Design Context, publishes
tasks to RabbitMQ queues, consumes results, and advances a simple state machine:
Implementation -> Lint -> Testbench -> Simulation -> Done (on pass).
On simulation failure, it runs Distill -> Reflect -> Debug and marks FAILED.
"""
from __future__ import annotations

import json
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

from orchestrator.context_builder import DemoContextBuilder
from orchestrator.state_machine import Node, NodeState
from orchestrator.task_memory import TaskMemory

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"


class DemoOrchestrator:
    """
    Drives a richer state machine:
        PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> SIMULATING -> DONE (on pass)
        SIMULATING (fail) -> DISTILLING -> REFLECTING -> DEBUGGING -> FAILED
    Persists logs/artifact paths to Task Memory. Testbench stage builds TB before simulation.
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
        self.dag = json.loads(dag_path.read_text())
        self.nodes: Dict[str, Node] = {n["id"]: Node(n["id"]) for n in self.dag["nodes"]}
        self.deps_map: Dict[str, set[str]] = {
            n["id"]: set(n.get("deps", []) or []) for n in self.dag["nodes"]
        }
        self.task_memory = TaskMemory(task_memory_root)
        self.state_callback = state_callback

    def _publish_task(self, ch: pika.adapters.blocking_connection.BlockingChannel, entity: EntityType, task_type: Any, node_id: str) -> TaskMessage:
        ctx = self.context_builder.build(node_id)
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
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.queue_declare(queue="results", durable=True)
            ch.queue_bind(queue="results", exchange=TASK_EXCHANGE, routing_key=RESULTS_ROUTING_KEY)

            node_ids = list(self.nodes.keys())
            tasks: Dict[str, Dict[str, TaskMessage | None]] = {}
            pending_nodes = set(node_ids)
            active_nodes = set()
            done_nodes = set()
            sim_failed_nodes = set()

            def _dump_model(payload: Any) -> Any:
                if payload is None:
                    return None
                if hasattr(payload, "model_dump"):
                    return payload.model_dump()
                if hasattr(payload, "dict"):
                    return payload.dict()
                return payload

            def _maybe_json(text: str) -> Any:
                try:
                    return json.loads(text)
                except Exception:
                    return text

            def start_node(node_id: str) -> None:
                self._advance(node_id, NodeState.IMPLEMENTING)
                impl_task = self._publish_task(ch, EntityType.REASONING, AgentType.IMPLEMENTATION, node_id)
                tasks[node_id] = {
                    "impl": impl_task,
                    "lint": None,
                    "tb": None,
                    "sim": None,
                    "distill": None,
                    "reflect": None,
                    "debug": None,
                }
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
                        if t and t.task_id == result.task_id:
                            target_node = node_id
                            stage = key
                            break
                    if target_node:
                        break
                if not target_node:
                    continue

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

                print(f"Result for {target_node} stage {stage}: {result.status.value}")
                if result.status is not TaskStatus.SUCCESS:
                    if stage == "sim":
                        sim_failed_nodes.add(target_node)
                        self._advance(target_node, NodeState.DISTILLING)
                        distill = self._publish_task(ch, EntityType.LIGHT_DETERMINISTIC, WorkerType.DISTILLATION, target_node)
                        tasks[target_node]["distill"] = distill
                        continue
                    self._advance(target_node, NodeState.FAILED)
                    active_nodes.discard(target_node)
                    done_nodes.add(target_node)
                    fail_dependents(target_node)
                    start_ready_nodes()
                    continue

                if stage == "impl":
                    self._advance(target_node, NodeState.LINTING)
                    lint_task = self._publish_task(ch, EntityType.LIGHT_DETERMINISTIC, WorkerType.LINTER, target_node)
                    tasks[target_node]["lint"] = lint_task
                elif stage == "lint":
                    self._advance(target_node, NodeState.TESTBENCHING)
                    tb_task = self._publish_task(ch, EntityType.REASONING, AgentType.TESTBENCH, target_node)
                    tasks[target_node]["tb"] = tb_task
                elif stage == "tb":
                    self._advance(target_node, NodeState.SIMULATING)
                    sim_task = self._publish_task(ch, EntityType.HEAVY_DETERMINISTIC, WorkerType.SIMULATOR, target_node)
                    tasks[target_node]["sim"] = sim_task
                elif stage == "sim":
                    self._advance(target_node, NodeState.DONE)
                    active_nodes.discard(target_node)
                    done_nodes.add(target_node)
                    start_ready_nodes()
                elif stage == "distill":
                    self._advance(target_node, NodeState.REFLECTING)
                    reflect = self._publish_task(ch, EntityType.REASONING, AgentType.REFLECTION, target_node)
                    tasks[target_node]["reflect"] = reflect
                elif stage == "reflect":
                    if target_node in sim_failed_nodes:
                        self._advance(target_node, NodeState.DEBUGGING)
                        debug = self._publish_task(ch, EntityType.REASONING, AgentType.DEBUG, target_node)
                        tasks[target_node]["debug"] = debug
                    else:
                        self._advance(target_node, NodeState.DONE)
                        active_nodes.discard(target_node)
                        done_nodes.add(target_node)
                        start_ready_nodes()
                elif stage == "debug":
                    self._advance(target_node, NodeState.FAILED)
                    active_nodes.discard(target_node)
                    done_nodes.add(target_node)
                    fail_dependents(target_node)
                    start_ready_nodes()

            if len(done_nodes) < len(node_ids):
                print("Demo timed out before all nodes completed.")
