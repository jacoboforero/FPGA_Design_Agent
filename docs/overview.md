# Overview

This project turns a frozen hardware spec into RTL, testbenches, lint/sim runs, and follow-on analysis with a mix of LLM agents and deterministic workers. Planning is a gate; execution is mechanical.

## How it flows
- **Plan** — Human + spec helper collect L1–L5, lock them, and the planner emits `design_context.json` + `dag.json`.
- **Execute** — The orchestrator walks the DAG: Implementation → Lint → Testbench → Simulation. On pass, the node is DONE. On sim failure, it runs Distill → Reflect → Debug and marks FAILED. Each stage writes logs/artifact paths to task memory.
- **Decide** — Coverage/results are reviewed; on failures you can use distill/reflect/debug outputs to iterate and re-run sim.

## What’s in scope now
- Local runs via CLI (LLM + toolchain required for end-to-end execution).
- Agents for implementation/testbench/reflection/debug/spec-helper; workers for lint/sim/distill.
- RabbitMQ queues with task memory persisted to disk.

## Where to read next
- Components and queues: [architecture.md](./architecture.md)
- Agent IO (inputs/outputs per role): [agents.md](./agents.md)
- CLI commands and examples: [cli.md](./cli.md)
- Planning checklist and artifacts: [spec-and-planning.md](./spec-and-planning.md)
- Queue/DLQ specifics: [queues-and-workers.md](./queues-and-workers.md)
