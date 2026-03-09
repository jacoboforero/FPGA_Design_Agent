# Architecture

The system is split into planning and execution. Planning freezes intent and interfaces up front. Execution then runs mechanically through queues and a state machine.

## Core Components
- **CLI**: collects specs, invokes planner, asks for execution confirmation, and starts workers/orchestrator.
- **Planner**: consumes frozen L1-L5 artifacts and emits design context + DAG.
- **Orchestrator**: starts ready nodes, publishes tasks, consumes results, advances node state, and applies retry/failure policy.
- **RabbitMQ broker**: routes tasks to agent and worker queues and captures rejected messages in DLQ.
- **Agents**: planner, specification helper, implementation, testbench, reflection, debug.
- **Deterministic workers**: lint, TB lint, simulation, acceptance, distillation.
- **Artifact stores**:
  - `artifacts/generated/`
  - `artifacts/task_memory/`
  - `artifacts/observability/`

## Execution Model
- DAG-driven scheduling with dependency gating.
- Per-task routing through broker exchange/queues.
- Run-scoped result routing (`RESULTS.<run_id>`) to isolate concurrent runs.
- Attempt tracking and bounded debug retries per failure reason.

## State Machine
- Main path:
  - `PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> TB_LINTING -> SIMULATING -> ACCEPTING -> DONE`
- Repair loop path:
  - `SIMULATING (fail) -> DISTILLING -> REFLECTING -> DEBUGGING -> retry`
  - `LINTING/TB_LINTING (fail) -> DEBUGGING -> retry`
- Dependents of a failed node can be marked `FAILED` without running.

## DLQ And Failure Isolation
- Queues are declared with `x-dead-letter-exchange`.
- Non-requeued rejections (`requeue=false`) are routed to `dead_letter_queue`.
- This prevents poison-pill tasks from blocking healthy work.

## Related Code
- `orchestrator/orchestrator_service.py`
- `orchestrator/state_machine.py`
- `core/runtime/broker.py`
- `infrastructure/rabbitmq-definitions.json`
