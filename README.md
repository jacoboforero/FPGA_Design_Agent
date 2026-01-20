# Multi-Agent Hardware Design System

LLM-backed agents plus deterministic workers that turn a frozen hardware spec into RTL, testbenches, lint/sim results, and analysis artifacts. Planning is frozen first; execution then runs mechanically through queues and a small state machine.

## What works today
- End-to-end pipeline via CLI (stubbed EDA path works without keys; LLM/tooling paths optional).
- Agents for implementation, testbench, reflection, debug, spec-helper; workers for lint, simulation, distillation.
- RabbitMQ-based orchestration with task memory under `artifacts/task_memory/` (CLI auto-purges per run).
- Multi-module specs supported in a single input; full TB/sim runs for the top module only.

## Quick start (containerized, recommended)
Use the pinned Verilator toolchain (5.044) inside Docker for consistent results across machines. The container also includes Icarus (`iverilog`/`vvp`) for simulation.

1) **Prereqs**
   - Docker + Docker Compose
   - Optional LLM: set `USE_LLM=1` and `OPENAI_API_KEY` (or Groq vars) in `.env`
2) **Build and start services**
   ```bash
   make build
   make up
   ```
3) **Install deps and run the CLI**
   ```bash
   make deps
   make cli
   ```
   Artifacts land in `artifacts/generated/rtl/`; logs live in `artifacts/task_memory/<node>/<stage>/` (cleared at each CLI run).
   `make deps` installs the OpenAI client extra required for LLM-backed agents.
   The container sets `EDITOR=nano`; override by setting `EDITOR` in `.env` if you prefer another editor.
   Inside Docker, `RABBITMQ_URL` must use the service host (`amqp://user:password@rabbitmq:5672/`).

## Host-only (not recommended)
You can still run on the host, but tool versions may drift across machines.

```bash
PYTHONPATH=. USE_LLM=1 python apps/cli/cli.py --timeout 120
```

## CLI usage
- `make cli` — runs the pipeline inside the pinned toolchain container (sources `.env` if present; CLI also loads it)
- `python apps/cli/cli.py` — host-only fallback (not recommended)

## Dev workflow helpers
- `make shell` — open a shell in the running app container (sources `.env` if present)
- `make test` — run pytest inside the container
- `make logs` — tail RabbitMQ logs
- `make down` — stop containers

## Devcontainer (VS Code)
Open the repo in a Dev Container to use the same pinned toolchain automatically. The config uses the `app` service in `infrastructure/docker-compose.yml`.

## Repo map (you’ll touch these)
- `apps/cli/` — main entrypoint
- `orchestrator/` — state machine, planner, task memory, context builder
- `agents/` — LLM-backed roles
- `workers/` — deterministic lint/sim/distill
- `core/schemas/` — contracts and enums
- `adapters/llm/` — gateway to OpenAI/Groq
- `infrastructure/` — RabbitMQ compose files
- `artifacts/generated/` — design context + RTL/TB outputs
- `artifacts/task_memory/` — per-stage logs and paths (cleared at each CLI run)
- `artifacts/observability/` — per-run event logs (`*_events.jsonl`) and LLM cost summaries
- `docs/` — deeper design notes

## Environment knobs
- Broker: `RABBITMQ_URL` (default `amqp://user:password@localhost:5672/`)
- LLM: `USE_LLM`, `LLM_PROVIDER` (`openai`/`groq`), `OPENAI_MODEL` (default `gpt-4.1-mini`) or `GROQ_MODEL`
- Tool overrides: `VERILATOR_PATH`, `IVERILOG_PATH`, `VVP_PATH`
- Sim failure window: `SIM_FAIL_WINDOW_BEFORE`, `SIM_FAIL_WINDOW_AFTER` (cycles around detected failure)

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
