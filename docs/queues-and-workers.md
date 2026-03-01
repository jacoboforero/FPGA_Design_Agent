# Queues and Workers

## Purpose
Specify queue routing and deterministic worker responsibilities.

## Audience
Engineers maintaining message routing, worker pools, and broker configuration.

## Scope
Broker-level and worker-level execution flow.

## Queues
- `agent_tasks` for reasoning/agent tasks
- `process_tasks` for light deterministic work
- `simulation_tasks` for heavy deterministic simulation tasks
- run-scoped result queue bound to `RESULTS.<run_id>`
- `dead_letter_queue` for rejected messages

## Task Lifecycle
1. Orchestrator publishes `TaskMessage`.
2. Queue routes by `entity_type`.
3. Worker/agent executes and publishes `ResultMessage`.
4. Orchestrator advances state or applies failure policy.

## Failure Handling
- Validation failures should route to DLQ (`requeue=false`).
- Transient failures are retried under configured policy.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/core/runtime/broker.py`
- `/home/jacobo/school/FPGA_Design_Agent/workers/`
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/rabbitmq-definitions.json`

## Related Docs
- [architecture.md](./architecture.md)
- [schemas.md](./schemas.md)
- [components/workers.md](./components/workers.md)
