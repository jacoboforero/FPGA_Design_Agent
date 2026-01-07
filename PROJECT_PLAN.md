# Project Completion Plan (Experiment Branch)

This branch keeps the full demo/runtime scaffolding. The plan below lists the code files that must be implemented or completed to deliver a fully working CLI flow end-to-end.

## Goals
- Orchestrate tasks from frozen specs/DAG through agents and deterministic workers.
- Produce RTL + testbenches, lint/sim/distill outputs, and persist task memory.
- Run via CLI entrypoints without manual patching; optional UI/extension remains demo-only.

## Work Items by Area

### Core Contracts & Gateway
- `core/schemas/contracts.py`, `core/schemas/specifications.py` — lock final message/validation schemas (inputs/outputs for every stage).
- `adapters/llm/` & `llm_gateway/` — wire provider selection, defaults, retries, logging; align agent usage with chosen models.
- `adapters/observability/agentops.py` — hook runtime events/metrics sink (or remove if unused).

### Orchestrator & Planner
- `orchestrator/state_machine.py` — finalize per-node lifecycle, transitions, retry/DLQ policy.
- `orchestrator/context_builder.py` — build task payloads (paths, specs, DAG metadata).
- `orchestrator/orchestrator_service.py` — broker loop, task publication, result handling, task memory persistence.
- `orchestrator/task_memory.py` — store logs/artifact paths per stage.
- `orchestrator/planner_stub.py` (or replacement planner) — generate validated design_context + DAG from specs; integrate with CLI.

### Agents (LLM-backed)
- `agents/implementation/worker.py`
- `agents/testbench/worker.py`
- `agents/reflection/worker.py`
- `agents/debug/worker.py`
- `agents/spec_helper/worker.py`

Implement per-agent contracts (inputs/outputs, artifacts, success/failure), integrate with LLM gateway, and add logging/metrics.

### Workers (Deterministic)
- `workers/lint/worker.py` — Verilator/HDL lint, emits logs/artifacts.
- `workers/sim/worker.py` — simulation driver, coverage metrics placeholder.
- `workers/distill/worker.py` — distill sim outputs to structured datasets.

Wire queue bindings, timeouts, and status reporting.

### CLI Entrypoints
- `apps/cli/run_full_demo.py` — drive planner → orchestrator → agents/workers; parameterize broker/config paths.
- `apps/cli/run_validation_report.py` — schema/report tooling; ensure compatibility with final schemas.
- `apps/ui_backend/server.py` & `apps/vscode-extension/` (optional/demo) — keep aligned with orchestrator API if maintained.

### Infrastructure & Config
- `infrastructure/docker-compose.yml`, `Docker/` — ensure RabbitMQ + (optional) lint/sim images; health checks.
- `.env.example` — complete required env vars (broker URL, LLM providers, tool paths, timeouts).
- `pytest.ini` / `tests/run_*` — align coverage targets and paths.

### Tests
- Expand `tests/infrastructure/` for queue bindings, message flow, DLQ/retry behavior.
- Expand `tests/core/schemas/` as schemas evolve.
- Add integration tests for orchestrator ↔ agents/workers with mocks where external tools/LLMs are unavailable.

### Docs
- `README.md` — up-to-date runbook for CLI usage.
- `docs/overview.md`, `docs/architecture.md`, `docs/agents.md`, `docs/spec-and-planning.md`, `docs/queues-and-workers.md`, `docs/schemas.md` — reflect finalized flows, configs, and artifacts layout.

## Delivery Sequence (Suggested)
1. Finalize schemas and LLM gateway defaults.
2. Implement orchestrator (state machine, broker loop, task memory) and planner.
3. Implement Implementation/Testbench agents and Lint/Sim workers; get end-to-end CLI run producing artifacts.
4. Add Reflection/Debug agents and Distill worker; introduce coverage/failure handling paths.
5. Harden observability, retries/DLQ, config/env handling.
6. Finish docs/tests and polish CLI ergonomics.
