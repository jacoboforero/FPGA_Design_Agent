# Architecture

Short map of the moving pieces. For the story, start with [overview.md](./overview.md); for agent IO see [agents.md](./agents.md).

## Components
- **Orchestrator** — reads `design_context.json` + `dag.json`, walks the DAG, publishes tasks, consumes results, advances state, and writes task memory.
- **RabbitMQ** — queues for agents (`agent_tasks`), deterministic work (`process_tasks`), simulations (`simulation_tasks`), results (`results`), and DLQ.
- **Agents (LLM-backed)** — spec-helper, planner, implementation, testbench, reflection, debug.
- **Workers (deterministic)** — RTL lint, testbench lint, acceptance gating, simulation, distillation.
- **Storage** — `artifacts/generated/` (design context + RTL/TB), `artifacts/task_memory/` (logs, artifact paths, insights; CLI auto-purges per run), and `artifacts/observability/` (per-run event logs and cost summaries).

## Execution path (per node)
`PENDING → IMPLEMENTING → LINTING → TESTBENCHING → TB_LINTING → SIMULATING → ACCEPTING → DONE` (on pass), or `SIMULATING → DISTILLING → REFLECTING → DEBUGGING → FAILED` on sim failure.

If testbench lint fails, the orchestrator skips sim and runs `DEBUGGING → FAILED`. If acceptance gating fails, the node is marked FAILED and dependents are blocked.

For multi-module runs, only the top module executes TB/SIM; submodules stop after lint and are marked DONE. The orchestrator enqueues the next task only when the prior stage returns `SUCCESS`. Distill/reflect/debug run only after sim failures.

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
