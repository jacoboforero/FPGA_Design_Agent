# Architecture

## Purpose
Describe core runtime components and how work is routed through the system.

## Audience
Engineers modifying orchestration, routing, planning, or execution internals.

## Scope
Component boundaries, queue topology, and state progression. Not a CLI manual.

## Core Components
- **Orchestrator**: reads design context and DAG, publishes tasks, consumes results, updates node state.
- **RabbitMQ**: routes reasoning, deterministic, and simulation work.
- **Agents**: planner, implementation, testbench, reflection, debug, specification helper.
- **Workers**: lint, testbench lint, simulation, acceptance, distillation.
- **Storage**:
  - `artifacts/generated/` for generated design artifacts
  - `artifacts/task_memory/` for stage logs and per-stage outputs
  - `artifacts/observability/` for event and cost telemetry

## State Progression
- Main success progression: `PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> TB_LINTING -> SIMULATING -> ACCEPTING -> DONE`.
- Repair-loop progression (when enabled): `SIMULATING -> DISTILLING -> REFLECTING -> DEBUGGING -> (LINTING/TB_LINTING/SIMULATING)`.

## Queue Routing (default)
- `REASONING` -> `agent_tasks`
- `LIGHT_DETERMINISTIC` -> `process_tasks`
- `HEAVY_DETERMINISTIC` -> `simulation_tasks`
- Results -> run-scoped `RESULTS.<run_id>` binding
- Rejects (`requeue=false`) -> DLQ

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/orchestrator_service.py`
- `/home/jacobo/school/FPGA_Design_Agent/core/runtime/broker.py`
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/rabbitmq-definitions.json`

## Related Docs
- [queues-and-workers.md](./queues-and-workers.md)
- [components/orchestrator.md](./components/orchestrator.md)
- [components/workers.md](./components/workers.md)
