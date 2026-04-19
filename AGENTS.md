# AGENTS.md

## Mission

This repository is a planning-first hardware design pipeline. Preserve the current shape unless a task explicitly requires otherwise:

- spec intake and refinement
- planning and design-context generation
- orchestrated agent and worker execution
- artifact, telemetry, and benchmark reporting

## First reads

- `README.md`
- `docs/README.md`
- `docs/architecture.md`
- `docs/cli.md`
- `docs/reference/codex-agentic-coding.md`

## Preferred environment

- Preferred local loop: `make build`, `make up`, `make deps`, then `make cli` or `make shell`.
- Host fallback: `poetry install --with dev`, then run repo commands as `PYTHONPATH=. poetry run python3 ...`.
- Broker-backed flows usually use `config/runtime.yaml` or `config/runtime.benchmark.yaml`.
- Prefer `make shell` or `make cli` over ad hoc container shells because they normalize `RABBITMQ_URL` for the Docker network.

## Repo map

- `apps/cli/`: primary entrypoints, doctor flow, benchmark commands, validation helpers
- `adapters/`: provider, RAG, and observability integrations
- `agents/`: LLM-backed stage workers
- `workers/`: deterministic lint, simulation, acceptance, and distillation stages
- `orchestrator/`: DAG execution, retries, and state transitions
- `core/runtime/`, `core/schemas/`, `core/prompting/`, `core/tools/`: shared contracts and infrastructure
- `prompts/`: prompt assets and reusable fragments
- `config/`: runtime manifests and domain configuration
- `docs/`: human runbooks and architecture notes
- `tests/`: verification suites that mostly mirror production packages

## Guardrails

- Keep changes scoped. Prefer targeted fixes over broad refactors.
- Do not change the core execution flow, broker routing shape, task/result contracts, or artifact layout unless the task explicitly requires it.
- Treat `core/schemas/`, `core/runtime/config.py`, `core/runtime/paths.py`, and orchestrator state transitions as stability boundaries.
- Do not edit generated benchmark or run outputs under `artifacts/` unless the task is explicitly about fixtures or sample artifacts.
- For larger or ambiguous work, follow the plan format in `PLANS.md` before making substantial edits.

## Validation

- Start with the narrowest relevant `pytest` target under `tests/`.
- `pytest tests/adapters -q`
- `pytest tests/agents -q`
- `pytest tests/apps -q`
- `pytest tests/cli -q`
- `pytest tests/core -q`
- `pytest tests/execution -q`
- `pytest tests/orchestrator -q`
- `pytest tests/workers -q`
- Run `python3 scripts/validate_docs.py` for doc changes.
- If prompts, CLI behavior, config loading, or shared runtime code changes, run the closest impacted tests before finishing.

## Prompting Codex in this repo

For non-trivial tasks, make the request explicit about:

- goal
- relevant files or docs
- constraints, especially architecture or behavior constraints
- done-when criteria and validation commands
