# Architecture

Short map of the moving pieces. For the story, start with [overview.md](./overview.md); for agent IO see [agents.md](./agents.md).

## Components
- **Orchestrator** — reads `design_context.json` + `dag.json`, walks the DAG, publishes tasks, consumes results, advances state, and writes task memory.
- **RabbitMQ** — queues for agents (`agent_tasks`), deterministic work (`process_tasks`), simulations (`simulation_tasks`), results (`results`), and DLQ.
- **Agents (LLM-backed)** — spec-helper, planner, implementation, testbench, reflection, debug.
- **Workers (deterministic)** — lint, simulation, distillation.
- **Storage** — `artifacts/generated/` (design context + RTL/TB) and `artifacts/task_memory/` (logs, artifact paths, insights).

## Execution path (per node)
`PENDING → IMPLEMENTING → LINTING → TESTBENCHING → SIMULATING → DISTILLING → REFLECTING → DONE` (or `FAILED`).

The orchestrator enqueues the next task only when the prior stage returns `SUCCESS`. Debug can be injected after sim failures if desired.

## Queue routing (defaults)
- `REASONING` → `agent_tasks`
- `LIGHT_DETERMINISTIC` → `process_tasks`
- `HEAVY_DETERMINISTIC` → `simulation_tasks`
- All completions → `results`
- Rejections (`requeue=false`) → DLQ via DLX

See [queues-and-workers.md](./queues-and-workers.md) for more on DLQ expectations.

## Planner inputs/outputs
- Inputs: locked L1–L5 specs in `artifacts/task_memory/specs/`
- Outputs: `artifacts/generated/design_context.json` and `dag.json` with module interfaces/paths and DAG nodes
- Paths in the design context are treated as targets; agents/workers write to them, orchestrator reads them.

## Config highlights
- Broker URL: `RABBITMQ_URL`
- LLM: `USE_LLM`, `LLM_PROVIDER`, model/env keys
- Tool overrides: `VERILATOR_PATH`, `IVERILOG_PATH`, `VVP_PATH`
- Timeouts are set in the runtimes (see code) and can be tuned per worker if needed.
