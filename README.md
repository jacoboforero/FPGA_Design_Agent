# Multi-Agent Hardware Design System

LLM-backed agents plus deterministic workers that turn a frozen hardware spec into RTL, testbenches, lint/sim results, and analysis artifacts. Planning is frozen first; execution then runs mechanically through queues and a small state machine.

## What works today
- End-to-end pipeline via CLI (stubbed EDA path works without keys; LLM/tooling paths optional).
- Agents for implementation, testbench, reflection, debug, spec-helper; workers for lint, simulation, distillation.
- RabbitMQ-based orchestration with task memory persisted under `artifacts/task_memory/`.

## Quick start (local)
1) **Prereqs**
   - Python 3.12+, `pip install -e .`
   - RabbitMQ: `cd infrastructure && docker-compose up -d`
   - Optional tools: Verilator (`verilator`), Icarus (`iverilog`, `vvp`)
   - Optional LLM: set `USE_LLM=1` and `OPENAI_API_KEY` (or Groq vars)
2) **Run pipeline (stub path)**
   ```bash
   PYTHONPATH=. USE_LLM=0 python apps/cli/cli.py run --allow-stub --timeout 60
   ```
   Artifacts land in `artifacts/generated/rtl/`; logs live in `artifacts/task_memory/<node>/<stage>/`.
3) **Run with LLM + tools** (after keys/tools are set)
   ```bash
   PYTHONPATH=. USE_LLM=1 python apps/cli/cli.py run --allow-stub --timeout 120
   ```

## CLI cheatsheet
- `python apps/cli/cli.py spec` — interactive L1–L5 collection and lock
- `python apps/cli/cli.py plan` — generate `design_context.json` + `dag.json` (uses locked specs or stub with `--stub/--allow-stub`)
- `python apps/cli/cli.py run` — full pipeline (planner → workers → orchestrator)
- `python apps/cli/cli.py lint --rtl <file>` — lint once
- `python apps/cli/cli.py sim --rtl <file> [--testbench <file>]` — simulate once

## Repo map (you’ll touch these)
- `apps/cli/` — main entrypoint
- `orchestrator/` — state machine, planner, task memory, context builder
- `agents/` — LLM-backed roles
- `workers/` — deterministic lint/sim/distill
- `core/schemas/` — contracts and enums
- `adapters/llm/` — gateway to OpenAI/Groq
- `infrastructure/` — RabbitMQ compose files
- `artifacts/generated/` — design context + RTL/TB outputs
- `artifacts/task_memory/` — per-stage logs and paths
- `docs/` — deeper design notes

## Environment knobs
- Broker: `RABBITMQ_URL` (default `amqp://user:password@localhost:5672/`)
- LLM: `USE_LLM`, `LLM_PROVIDER` (`openai`/`groq`), `OPENAI_MODEL` (default `gpt-4.1-mini`) or `GROQ_MODEL`
- Tool overrides: `VERILATOR_PATH`, `IVERILOG_PATH`, `VVP_PATH`

## Testing
- Unit/schema: `pytest tests/core/schemas -q`
- Workers/planner smoke: `pytest tests/workers/test_* tests/core/test_planner.py`

## Docs (start here)
- `docs/overview.md` — how the system flows
- `docs/architecture.md` — components and queues
- `docs/agents.md` — role-by-role IO
- `docs/cli.md` — command details
- `docs/observability.md` — AgentOps setup and cost tracking
- `docs/spec-and-planning.md` — L1–L5 checklist and artifacts
- `docs/queues-and-workers.md` — broker layout and DLQ notes
