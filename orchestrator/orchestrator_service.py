"""
Minimal orchestrator for the demo. Loads DAG and Design Context, publishes
tasks to RabbitMQ queues, consumes results, and advances a simple state machine:
Implementation -> Lint -> Simulation -> Done
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
        PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> SIMULATING -> DISTILLING -> REFLECTING -> DONE
    Adds coverage gating (mocked) and persists logs/artifact paths to Task Memory. Testbench stage builds TB before simulation.
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
        self.deps: Dict[str, list[str]] = {n["id"]: n.get("deps", []) for n in self.dag["nodes"]}
        self.task_memory = TaskMemory(task_memory_root)
        self.state_callback = state_callback

    def _publish_task(
        self,
        ch: pika.adapters.blocking_connection.BlockingChannel,
        entity: EntityType,
        task_type: Any,
        node_id: str,
        extra_context: Dict[str, Any] | None = None,
    ) -> TaskMessage:
        ctx = {**self.context_builder.build(node_id)}
        if extra_context:
            ctx.update(extra_context)
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
        print(f"[Orchestrator] {node_id} -> {new_state.value}")
        emit_runtime_event(runtime="orchestrator", event_type="state_transition", payload={"node_id": node_id, "state": new_state.value})
        if self.state_callback:
            self.state_callback(node_id, new_state.value)

    def run(self, timeout_s: float = 30.0) -> None:
        with pika.BlockingConnection(self.connection_params) as conn:
            ch = conn.channel()
            ch.queue_declare(queue="results", durable=True)
            ch.queue_bind(queue="results", exchange=TASK_EXCHANGE, routing_key=RESULTS_ROUTING_KEY)

            node_ids = list(self.nodes.keys())
            tasks: Dict[str, Dict[str, TaskMessage]] = {
                nid: {"impl": None, "lint": None, "tb": None, "sim": None, "distill": None, "reflect": None, "debug": None}
                for nid in node_ids
            }
            failure_context: Dict[str, Dict[str, Any]] = {}

            start = time.time()
            done_nodes = set()

            while time.time() - start < timeout_s and len(done_nodes) < len(node_ids):
                # Schedule ready nodes (dependencies satisfied)
                for nid in node_ids:
                    if self.nodes[nid].state == NodeState.PENDING:
                        deps = self.deps.get(nid, [])
                        if all(dep in done_nodes for dep in deps):
                            self._advance(nid, NodeState.IMPLEMENTING)
                            impl_task = self._publish_task(ch, EntityType.REASONING, AgentType.IMPLEMENTATION, nid)
                            tasks[nid]["impl"] = impl_task

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

                log_path = self.task_memory.record_log(target_node, stage, result.log_output)
                if result.artifacts_path:
                    self.task_memory.record_artifact_path(target_node, stage, result.artifacts_path)

                print(f"[Orchestrator] Result for {target_node} stage {stage}: {result.status.value}")

                # Stage handling
                if stage == "lint" and result.status is not TaskStatus.SUCCESS:
                    failure_context[target_node] = {
                        "failure_stage": "lint",
                        "failure_log": result.log_output,
                        "failure_log_path": str(log_path),
                        "rtl_path": self.context_builder.build(target_node).get("rtl_path"),
                    }
                    self._advance(target_node, NodeState.DEBUGGING)
                    debug_task = self._publish_task(
                        ch,
                        EntityType.REASONING,
                        AgentType.DEBUG,
                        target_node,
                        extra_context=failure_context.get(target_node),
                    )
                    tasks[target_node]["debug"] = debug_task
                    continue

                if stage == "sim" and result.status is not TaskStatus.SUCCESS:
                    failure_context[target_node] = {
                        "failure_stage": "sim",
                        "failure_log": result.log_output,
                        "failure_log_path": str(log_path),
                        "failure_artifact_path": result.artifacts_path,
                    }
                    # On simulation failure, distill waveforms/logs and reflect.
                    self._advance(target_node, NodeState.DISTILLING)
                    distill = self._publish_task(
                        ch,
                        EntityType.LIGHT_DETERMINISTIC,
                        WorkerType.DISTILLATION,
                        target_node,
                        extra_context=failure_context.get(target_node),
                    )
                    tasks[target_node]["distill"] = distill
                    continue

                if result.status is not TaskStatus.SUCCESS:
                    self._advance(target_node, NodeState.FAILED)
                    done_nodes.add(target_node)
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
                    # Sim success: mark done (no distill/reflect on success).
                    self._advance(target_node, NodeState.DONE)
                    done_nodes.add(target_node)
                elif stage == "distill":
                    self._advance(target_node, NodeState.REFLECTING)
                    extra = failure_context.get(target_node, {}).copy()
                    if result.distilled_dataset:
                        extra["distilled_dataset"] = result.distilled_dataset.model_dump()
                    reflect = self._publish_task(ch, EntityType.REASONING, AgentType.REFLECTION, target_node, extra_context=extra)
                    tasks[target_node]["reflect"] = reflect
                elif stage == "reflect":
                    if result.reflection_insights is not None:
                        self.task_memory.record_reflection(target_node, result.reflection_insights.model_dump_json())  # type: ignore[arg-type]
                    # Chain into debug for concrete fix suggestions.
                    debug_ctx = failure_context.get(target_node, {}).copy()
                    if result.reflection_insights is not None:
                        debug_ctx["reflection_insights"] = result.reflection_insights.model_dump()
                    debug_task = self._publish_task(ch, EntityType.REASONING, AgentType.DEBUG, target_node, extra_context=debug_ctx)
                    tasks[target_node]["debug"] = debug_task
                elif stage == "debug":
                    if result.status is TaskStatus.SUCCESS:
                        self._advance(target_node, NodeState.DONE)
                    else:
                        self._advance(target_node, NodeState.FAILED)
                    done_nodes.add(target_node)

            if len(done_nodes) < len(node_ids):
                print("[Orchestrator] Demo timed out before all nodes completed.")
