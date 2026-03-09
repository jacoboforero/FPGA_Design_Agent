# Queues and Workers

Tasks are published by orchestrator and consumed by agent or deterministic worker runtimes through RabbitMQ routing.

## Queue Topology
Dedicated queues exist per task type (for example `agent_impl_tasks`, `process_lint_tasks`, `process_tb_lint_tasks`, `simulation_tasks`) plus compatibility legacy queues (`agent_tasks`, `process_tasks`, `simulation_tasks`).

Results are consumed through run-scoped bindings:
- `RESULTS.<run_id>`

Rejected tasks are dead-lettered to:
- `dead_letter_queue`

## Routing Model
- Orchestrator publishes `TaskMessage` to `tasks_exchange` with routing key derived from task type.
- Workers/agents consume matching queues.
- Each worker/agent publishes `ResultMessage` back to task exchange using the task's `results_routing_key`.

## Deterministic Worker Responsibilities
- **Lint worker**: RTL lint and semantic checks.
- **TB lint worker**: TB compile/lint checks.
- **Simulation worker**: compile/run simulation, capture waveform/log output.
- **Acceptance worker**: enforce acceptance gate checks.
- **Distillation worker**: reduce failing simulation logs/waveforms into compact debugging dataset.

## DLQ Behavior
- Invalid payloads or unrecoverable failures should be NACKed with `requeue=false`.
- Queue declarations include DLX routing so poison-pill tasks are isolated without blocking normal traffic.

## Related Code
- `core/runtime/broker.py`
- `workers/`
- `infrastructure/rabbitmq-definitions.json`
- `tests/infrastructure/test_dlq_functionality.py`
