"""
FastAPI bridge to expose the demo orchestrator state over HTTP for the VS Code extension.
Endpoints:
- POST /run : start a demo run (planner + orchestrator + workers)
- GET /state : returns node states and log tails
- GET /logs/{node_id} : returns concatenated logs for a node

This server runs workers in background threads and spawns an orchestrator per run.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List

import shutil
import pika
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.planner.worker import PlannerWorker
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus

TASK_EXCHANGE = "tasks_exchange"
RESULTS_ROUTING_KEY = "RESULTS"
from orchestrator.orchestrator_service import DemoOrchestrator
from agents.implementation.worker import ImplementationWorker
from agents.testbench.worker import TestbenchWorker
from agents.reflection.worker import ReflectionWorker
from agents.debug.worker import DebugWorker
from agents.spec_helper.worker import SpecHelperWorker
from workers.lint.worker import LintWorker
from workers.sim.worker import SimulationWorker
from workers.distill.worker import DistillWorker
from agents.common.llm_gateway import init_llm_gateway, Message, MessageRole, GenerationConfig

ARTIFACTS = REPO_ROOT / "artifacts" / "generated"
TASK_MEMORY = REPO_ROOT / "artifacts" / "task_memory"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state_lock = threading.Lock()
node_state: Dict[str, Dict] = {}
workers_started = False
stop_event = threading.Event()
chat_history: List[Dict[str, str]] = []
spec_helper_gateway = None


def init_spec_helper_gateway():
    """Initialize shared LLM gateway for the spec helper chat."""
    global spec_helper_gateway
    spec_helper_gateway = init_llm_gateway()
    return spec_helper_gateway


def state_callback(node_id: str, new_state: str) -> None:
    with state_lock:
        if node_id not in node_state:
            node_state[node_id] = {"id": node_id}
        node_state[node_id]["state"] = new_state
        node_state[node_id]["logTail"] = tail_logs(node_id)

def reset_state():
    with state_lock:
        node_state.clear()
    # clear task memory for fresh demo run
    if TASK_MEMORY.exists():
        shutil.rmtree(TASK_MEMORY)
    TASK_MEMORY.mkdir(parents=True, exist_ok=True)
    chat_history.clear()


def tail_logs(node_id: str) -> str:
    logs: List[str] = []
    node_dir = TASK_MEMORY / node_id
    if not node_dir.exists():
        return ""
    for stage in sorted(node_dir.iterdir()):
        log_file = stage / "log.txt"
        if log_file.exists():
            logs.append(f"[{stage.name}] {log_file.read_text().strip()}")
    return "\n".join(logs[-3:]) if logs else ""


def start_workers(params: pika.ConnectionParameters) -> List[threading.Thread]:
    global workers_started
    if workers_started:
        return []
    workers_started = True
    threads = [
        PlannerWorker(params, stop_event),
        ImplementationWorker(params, stop_event),
        TestbenchWorker(params, stop_event),
        ReflectionWorker(params, stop_event),
        DebugWorker(params, stop_event),
        SpecHelperWorker(params, stop_event),
        LintWorker(params, stop_event),
        DistillWorker(params, stop_event),
        SimulationWorker(params, stop_event),
    ]
    for t in threads:
        t.start()
    return threads


def run_planner_task(params: pika.ConnectionParameters, timeout: float = 30.0) -> None:
    task = TaskMessage(
        entity_type=EntityType.REASONING,
        task_type=AgentType.PLANNER,
        context={
            "spec_dir": str(REPO_ROOT / "artifacts" / "task_memory" / "specs"),
            "out_dir": str(REPO_ROOT / "artifacts" / "generated"),
        },
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        ch.queue_declare(queue="results", durable=True)
        ch.queue_bind(queue="results", exchange=TASK_EXCHANGE, routing_key=RESULTS_ROUTING_KEY)
        ch.basic_publish(
            exchange=TASK_EXCHANGE,
            routing_key=task.entity_type.value,
            body=task.model_dump_json().encode(),
            properties=pika.BasicProperties(content_type="application/json"),
        )
        start = time.time()
        while time.time() - start < timeout:
            method, props, body = ch.basic_get(queue="results", auto_ack=True)
            if body is None:
                continue
            result = ResultMessage.model_validate_json(body)
            if result.task_id != task.task_id:
                continue
            if result.status is not TaskStatus.SUCCESS:
                raise HTTPException(status_code=400, detail=f"Planning failed: {result.log_output}")
            return
    raise HTTPException(status_code=504, detail="Planner timed out waiting for results.")


@app.post("/run")
def run_demo():
    rabbit_url = os.getenv("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    try:
        params = pika.URLParameters(rabbit_url)
        conn = pika.BlockingConnection(params)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"RabbitMQ not reachable: {exc}")

    reset_state()
    init_spec_helper_gateway()
    threads = start_workers(params)
    run_planner_task(params)
    orch = DemoOrchestrator(
        params,
        ARTIFACTS / "design_context.json",
        ARTIFACTS / "dag.json",
        ARTIFACTS,
        TASK_MEMORY,
        state_callback=state_callback,
    )
    t = threading.Thread(target=orch.run, daemon=True)
    t.start()
    return {"status": "started"}


@app.post("/reset")
def reset_demo_state():
    """
    Clears in-memory node state, chat history, and artifacts/task_memory artifacts.
    Does not stop running workers; use before starting a new demo run.
    """
    reset_state()
    return {"status": "reset"}


@app.get("/state")
def get_state():
    with state_lock:
        nodes = list(node_state.values())
    return {"nodes": nodes}


@app.get("/logs/{node_id}")
def get_logs(node_id: str):
    node_dir = TASK_MEMORY / node_id
    if not node_dir.exists():
        raise HTTPException(status_code=404, detail="node not found")
    logs: List[str] = []
    for stage in sorted(node_dir.iterdir()):
        log_file = stage / "log.txt"
        if log_file.exists():
            logs.append(f"[{stage.name}]\n{log_file.read_text()}")
    return {"node": node_id, "logs": "\n\n".join(logs)}


@app.get("/chat")
def get_chat_history():
    return {"history": chat_history}


@app.post("/chat")
async def send_chat(message: Dict[str, str]):
    user_msg = message.get("message", "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="empty message")

    chat_history.append({"role": "user", "content": user_msg})
    init_spec_helper_gateway()
    reply = await generate_spec_helper_reply(user_msg)
    chat_history.append({"role": "agent", "content": reply})
    return {"reply": reply, "history": chat_history}


@app.post("/chat/reset")
def reset_chat():
    chat_history.clear()
    return {"history": chat_history}


async def generate_spec_helper_reply(user_msg: str) -> str:
    """
    LLM-backed spec helper for the UI chat.
    """
    if os.getenv("USE_LLM") != "1" or not spec_helper_gateway or not Message or not MessageRole or not GenerationConfig:
        raise HTTPException(status_code=503, detail="LLM unavailable; enable USE_LLM=1 and configure provider credentials.")
    system = (
        "You are the Specification Helper Agent for RTL designs. "
        "You extract and refine L1-L5: intent, interface, verification goals/coverage, architecture/clocking, acceptance. "
        "Return a short structured summary and 2-3 clarifying questions if needed. "
        "Be concise; prefer bullet lists."
    )
    msgs: List[Message] = [Message(role=MessageRole.SYSTEM, content=system)]
    for m in chat_history[-6:]:
        role = m.get("role", "user")
        if role == "agent":
            msgs.append(Message(role=MessageRole.ASSISTANT, content=m["content"]))
        else:
            msgs.append(Message(role=MessageRole.USER, content=m["content"]))
    msgs.append(Message(role=MessageRole.USER, content=user_msg))
    cfg = GenerationConfig(temperature=0.2, max_tokens=500)
    resp = await spec_helper_gateway.generate(messages=msgs, config=cfg)  # type: ignore
    return resp.content
