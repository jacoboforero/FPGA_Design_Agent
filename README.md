# Multi-Agent Hardware Design System

## Purpose
Provide a practical entrypoint to run and maintain this repository's planning + RTL generation pipeline.

## Audience
Developers and maintainers operating the CLI pipeline, brokered workers, and benchmark workflows.

## Scope
Quick-start operations and pointers to deeper docs. Detailed component internals live under `docs/`.

LLM-backed agents plus deterministic workers that turn a frozen hardware spec into RTL, testbenches, lint (RTL/TB), sim results, and analysis artifacts. Planning is frozen first; execution then runs mechanically through queues and a small state machine.

## What works today
- End-to-end pipeline via CLI (stubbed EDA path works without keys; LLM/tooling paths optional).
- Agents for implementation, testbench, reflection, debug, spec-helper; workers for RTL lint, testbench lint, acceptance gating, simulation, distillation.
- RabbitMQ-based orchestration with task memory under `artifacts/task_memory/` (CLI auto-purges per run).
- Multi-module specs supported in a single input; full TB/sim runs for the top module only.

## Quick start (containerized, recommended)
Use the pinned Verilator toolchain (5.044) inside Docker for consistent results across machines. The container also includes Icarus (`iverilog`/`vvp`) for testbench lint and simulation.

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
- `workers/` — deterministic RTL lint / testbench lint / acceptance gating / sim / distill
- `core/schemas/` — contracts and enums
- `adapters/llm/` — gateway to OpenAI/Groq
- `infrastructure/` — RabbitMQ compose files
- `artifacts/generated/` — design context + RTL/TB outputs
- `artifacts/task_memory/` — per-stage logs and paths (cleared at each CLI run)
- `artifacts/observability/` — per-run event logs (`*_events.jsonl`) and LLM cost summaries
- `docs/` — deeper design notes

## Configuration
- Runtime behavior: `config/runtime.yaml` (override with `--config`, preset via `--preset`)
- Secrets/credentials: environment variables (`OPENAI_API_KEY`, `GROQ_API_KEY`, AgentOps keys)
- Broker/tool/LLM/lint/sim/debug policy knobs are YAML-driven in the runtime config.

## Testing
- Unit/schema: `pytest tests/core/schemas -q`
- Workers/planner smoke: `pytest tests/workers/test_* tests/core/test_planner.py`

## Docs (start here)
- `docs/README.md` — master documentation index
- `docs/components/` — component internals (orchestrator, workers, gateway, UI bridge)
- `docs/workflows/` — operational runbooks (interactive, benchmark, failure loop)
- `docs/reference/` — command and config references
- `docs/overview.md` — high-level lifecycle
- `docs/architecture.md` — component map and state progression
- `docs/cli.md` — command-line usage

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/cli.py`
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/orchestrator_service.py`
- `/home/jacobo/school/FPGA_Design_Agent/config/runtime.yaml`

## Related Docs
- [docs/README.md](/home/jacobo/school/FPGA_Design_Agent/docs/README.md)
- [docs/workflows/interactive-run.md](/home/jacobo/school/FPGA_Design_Agent/docs/workflows/interactive-run.md)
