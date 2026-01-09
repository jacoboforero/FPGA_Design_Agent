# Project completion plan (experiment branch)

This branch keeps the full demo/runtime. The goal is a turnkey CLI flow that takes locked specs to RTL/TB, lint/sim, and analysis with clear artifacts and docs.

## Goals
- End-to-end pipeline runs from locked specs/DAG through agents and workers.
- RTL + TB + lint/sim/distill outputs are persisted; task memory is readable.
- CLI is the primary entrypoint; UI/extension stay optional.

## Work items
- **Contracts & gateway:** finalize `core/schemas/*`; tighten LLM gateway defaults, retries, and logging; drop unused observability stubs or wire a sink.
- **Orchestrator & planner:** finalize lifecycle/transition policy, context builder, task memory, broker loop; replace stub planner with agent when ready.
- **Agents:** implementation, testbench, reflection, debug, spec-helper — define inputs/outputs, success predicates, and logs; ensure interface adherence.
- **Workers:** lint (Verilator), sim (iverilog/vvp), distill — enforce timeouts, DLQ policy, and artifact/log paths.
- **CLI/UI:** keep `apps/cli/cli.py` the source of truth; align FastAPI bridge/VS Code extension if maintained.
- **Infrastructure:** RabbitMQ compose/defs; `.env.example` with broker, LLM, tool paths; pytest config.
- **Tests:** expand schema + integration (queue flow, DLQ); add worker/agent fallbacks and optional real-tool/LLM jobs.
- **Docs:** keep README + `docs/*` aligned with the implemented flow (CLI-first).

## Suggested sequence
1) Freeze schemas and LLM gateway defaults.  
2) Harden orchestrator, planner, and task memory.  
3) Ship Implementation/Testbench + Lint/Sim for a passing end-to-end run.  
4) Add Distill/Reflection/Debug loop and coverage hooks.  
5) Polish observability, retries/DLQ, and config.  
6) Finalize docs/tests and CLI ergonomics.
