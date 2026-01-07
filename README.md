# Multi-Agent Hardware Design System

LLM-driven agents + deterministic workers that take frozen hardware intent to verified RTL/testbenches through a queued, state-machine-controlled flow. Planning (L1–L5) is frozen first; execution then runs mechanically.

## Runtime Layout

- `apps/cli/` — human entrypoints for demos and validation reports  
- `apps/ui_backend/` — FastAPI bridge for the VS Code extension; spawns orchestrator + workers  
- `apps/vscode-extension/` — frontend extension assets  
- `core/schemas/` — shared message contracts; `core/observability/` defines structured events  
- `orchestrator/` — control plane, state machine, task memory utils, demo `planner_stub.py` (temporarily kept here)  
- `agents/` — per-role agent runtimes (implementation, testbench, debug, reflection, spec helper)  
- `workers/` — deterministic runtimes (lint, simulation, distillation)  
- `adapters/llm/` — LLM provider integrations; `adapters/observability/agentops.py` sink placeholder  
- `artifacts/generated/`, `artifacts/task_memory/` — generated design context/RTL and runtime outputs  
- `tests/core/schemas/`, `tests/infrastructure/` — contract and infrastructure suites  
- `docs/` — architecture/process docs  

## Quick Start

### Broker (RabbitMQ)

```bash
cd infrastructure
docker-compose up -d        # start broker
docker-compose ps           # verify
# docker-compose down       # stop
```

- UI: http://localhost:15672 (user/password)  
- AMQP: amqp://user:password@localhost:5672/  
- Queues: `agent_tasks`, `process_tasks`, `simulation_tasks`, `dead_letter_queue`

### Demo run (stubbed EDA)

```bash
# Planner stub → orchestrator → workers → task memory artifacts
python apps/cli/run_full_demo.py
```

### FastAPI bridge (used by VS Code extension)

```bash
python apps/ui_backend/server.py
```

Endpoints: `POST /run`, `GET /state`, `GET /logs/{node}`, `GET/POST /chat`, `POST /chat/reset`, `POST /reset` (clears `artifacts/task_memory`).

### LLM configuration

- Set `USE_LLM=1`.  
- OpenAI: `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, optional `OPENAI_MODEL` (defaults gpt-4.1-mini).  
- Groq: `LLM_PROVIDER=groq`, `GROQ_API_KEY`, optional `GROQ_MODEL` (e.g., `llama-3.1-8b-instant`).  
- Spec Helper chat uses the same gateway; falls back to mock parsing when unset.

### CLI

- `python apps/cli/cli.py plan` — generate planner outputs  
- `python apps/cli/cli.py run` — full pipeline (planner → workers → orchestrator)  
- `python apps/cli/cli.py lint --rtl path/to/file.sv`  
- `python apps/cli/cli.py sim --rtl path/to/file.sv --testbench path/to/tb.sv`

## Tests

- Contracts: `pytest tests/core/schemas -q`  
- Infrastructure: `python run_infrastructure_tests.py` or `pytest tests/infrastructure -v`  

## Documentation

- `docs/overview.md` — planning/execution tour (planner stub lives in `orchestrator/` for now)  
- `docs/architecture.md` — runtime topology and queues  
- `docs/agents.md` — agent roles  
- `docs/spec-and-planning.md` — L1–L5 checklist; artifacts under `artifacts/task_memory/specs/`  
- `docs/queues-and-workers.md` — broker/DLQ details  
- `docs/schemas.md` + `core/schemas/SCHEMAS.md` — message contracts  
