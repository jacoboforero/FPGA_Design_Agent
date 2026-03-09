# Multi-Agent Hardware Design System

This repository provides a planning-first hardware generation pipeline: freeze spec intent, generate a design context/DAG, then execute implementation and verification through brokered workers.

## What Works Today
- End-to-end CLI pipeline for planning + execution.
- LLM-backed agents: spec helper, planner, implementation, testbench, reflection, debug.
- Deterministic workers: RTL lint, TB lint, simulation, acceptance, distillation.
- RabbitMQ-based orchestration with task memory artifacts per stage.
- Multi-module spec support with top-level execution flow.
- Research benchmark workflow with explicit run/analyze/compare/list command modes.

## Choose Your Path
### Hardware engineer path
1. Run interactive/full CLI flow.
2. Refine spec and approve planning handoff.
3. Execute and inspect generated RTL + verification artifacts.

Primary docs:
- [docs/workflows/interactive-run.md](docs/workflows/interactive-run.md)
- [docs/spec-and-planning.md](docs/spec-and-planning.md)

### Researcher path
1. Run benchmark preflight checks.
2. Execute reproducible benchmark runs/campaigns.
3. Compare and interpret benchmark outcomes.

Primary docs:
- [docs/workflows/benchmark-run.md](docs/workflows/benchmark-run.md)
- [docs/workflows/benchmark-campaigns.md](docs/workflows/benchmark-campaigns.md)
- [docs/benchmark-methodology.md](docs/benchmark-methodology.md)

## Quick Start (Containerized Recommended)
Use the pinned container toolchain for reproducible behavior.

1. Prerequisites
- Docker + Docker Compose
- Optional LLM keys (`OPENAI_API_KEY` or `GROQ_API_KEY`) in `.env`

2. Build and start
```bash
make build
make up
```

3. Install deps and run CLI
```bash
make deps
make cli
```

Generated outputs go to `artifacts/generated/`, stage logs to `artifacts/task_memory/`, and run telemetry to `artifacts/observability/`.

## Host Fallback
```bash
PYTHONPATH=. python3 apps/cli/cli.py --timeout 120 --config config/runtime.yaml --preset engineer_fast
```

## Common Commands
```bash
PYTHONPATH=. python3 apps/cli/cli.py --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py benchmark run --preset benchmark --campaign smoke
PYTHONPATH=. python3 apps/cli/cli.py benchmark compare --left-dir <run_a>/canonical --right-dir <run_b>/canonical
```

## Repo Map
- `apps/cli/` main entrypoints
- `orchestrator/` scheduling, state machine, task memory integration
- `agents/` LLM-backed task handlers
- `workers/` deterministic execution stages
- `core/schemas/` shared contracts
- `core/runtime/` broker/config/retry helpers
- `infrastructure/` RabbitMQ and container setup
- `artifacts/` generated outputs and observability traces
- `docs/` detailed architecture and runbooks

## Configuration
- Runtime behavior: `config/runtime.yaml`
- Secrets and credentials: environment variables
- Use `--config` and `--preset` to select run profile behavior.

## Testing
```bash
pytest tests/core/schemas -q
pytest tests/infrastructure -q
pytest tests/workers -q
pytest tests/execution -q
pytest tests/orchestrator -q
pytest tests/apps/test_run_verilog_eval.py -q
pytest tests/apps/test_run_benchmark_campaign.py -q
pytest tests/apps/test_index_runs.py -q
```

## Documentation
- [docs/README.md](docs/README.md)
- [docs/vision-and-ux.md](docs/vision-and-ux.md)
- [docs/overview.md](docs/overview.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/workflows/interactive-run.md](docs/workflows/interactive-run.md)
- [docs/workflows/benchmark-run.md](docs/workflows/benchmark-run.md)
