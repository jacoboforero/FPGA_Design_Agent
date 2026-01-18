# Queues & workers

RabbitMQ is the glue between the orchestrator and every runtime. Keep the routing simple and fail fast to DLQ on bad inputs.

## Queues
- `agent_tasks` — LLM agents (spec-helper, planner, implementation, testbench, reflection, debug)
- `process_tasks` — deterministic/light work (lint, distill, misc tooling)
- `simulation_tasks` — heavier runs (sim)
- `results` — all completions land here
- `dead_letter_queue` — DLX target for rejected messages

## Lifecycle (per task)
1) Orchestrator builds `TaskMessage` with routing and context.  
2) Message goes to the right queue (`agent_tasks`/`process_tasks`/`simulation_tasks`).  
3) Worker consumes, does the work, and publishes `ResultMessage` to `results`.  
4) Orchestrator updates state and enqueues the next stage.

## DLQ expectations
- Validate inputs first; if schema/interface is wrong, NACK with `requeue=false` (DLQ).
- Retry only once for transient LLM/tool failures; otherwise DLQ to avoid clogging queues.
- DLQ keeps headers (task_id, correlation_id, routing key, failure count) for triage.

## Worker pools (default routing keys)
- `REASONING` → agents
- `LIGHT_DETERMINISTIC` → lint/distill
- `HEAVY_DETERMINISTIC` → simulation

See [schemas.md](./schemas.md) for the controlled vocabularies (`AgentType`, `WorkerType`, `EntityType`, `TaskStatus`, etc.).
