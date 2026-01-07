# Queues & Workers

This doc covers how tasks flow through RabbitMQ, how worker pools consume them, and how the DLX/DLQ protects the system. For logical architecture see [architecture.md](./architecture.md); for agent behaviors see [agents.md](./agents.md).

## Queue Inventory

- `agent_tasks`: LLM agent work (implementation, testbench, debug, reflection, spec-helper, planning).  
- `process_tasks`: Deterministic tasks such as linting, compilation, distillation.  
- `simulation_tasks`: Long-running simulations.  
- `results`: Completion notifications consumed by the Orchestrator.  
- `dead_letter_queue` (via DLX): Quarantine for rejected/poison-pill tasks.

## Task Lifecycle

1. **Creation:** Orchestrator identifies a ready state transition in the DAG and builds a `TaskMessage` with routing info and context.  
2. **Dispatch:** The message is published to the appropriate queue (`agent_tasks`, `process_tasks`, or `simulation_tasks`).  
3. **Consumption:** A worker in the matching pool acknowledges the message and executes. Agents and deterministic workers run independently; they never call each other directly.  
4. **Result:** Worker publishes a `ResultMessage` to `results`, including artifacts/logs/metrics.  
5. **State Update:** Orchestrator consumes `results`, updates artifact state, and may enqueue follow-on tasks (e.g., implementation → lint → **testbench** → simulation → distill → reflect).

## Poison Pills and DLX/DLQ

- **Poison pill:** A `TaskMessage` that cannot be successfully processed by its intended worker (schema violations, unrecoverable deterministic failures, semantic contradictions with the frozen Design Context).  
- **Detection:** Workers validate inputs and guard critical sections; fixed retry limits are allowed for transient errors.  
- **Rejection:** Once deemed unrecoverable, the worker issues a negative acknowledgment with `requeue=false`.  
- **DLX routing:** The broker’s Dead Letter Exchange automatically routes rejected messages—preserving headers such as `task_id`, `correlation_id`, original routing key, failure count, and rejection reason—to the DLQ.  
- **Isolation:** DLQ quarantine prevents poison pills from starving primary queues while healthy traffic proceeds.

## DLQ Monitor & Alerter

- Tracks DLQ depth, message age, and failure signatures.  
- Emits alerts to the human maintainer when thresholds breach SLOs.  
- Supports controlled replay after remediation; DLQ write access is gated to avoid reintroducing poison pills.

## Worker Pools in Context

- **Agent Pool:** Hosted by the agent-worker runtime; selected via `AgentType` per task.  
- **Deterministic Pools:** Hosted by the deterministic-workers runtime for lint/compile/distill and the simulation pool for long-running sims.  
- **Orchestrator:** Sole producer of tasks and consumer of results; consults Design Context/task state only.  
- **Task Memory:** Stores per-task artifacts (logs, distilled datasets, reflection outputs, metrics) that inform retries and escalations.

## Schema Invariants

Workers must validate inbound messages against shared schemas before processing. Controlled vocabularies (`AgentType`, `WorkerType`, `EntityType`, `TaskPriority`, `TaskStatus`) and payload validation help prevent malformed tasks from circulating. See [schemas.md](./schemas.md) for the canonical definitions.

## Validation/Retry/DLQ Guidance (by role)

- **All roles:** validate required context fields; reject to DLQ on schema/interface mismatch. Retry only transient LLM/tool errors once; log model/tool and assumptions.
- **Implementation/Testbench:** DLQ on missing interface or repeated generation failure; timeout ~60–120s.
- **Reflection/Debug:** DLQ on missing required inputs (distilled data, reflection insights, failure signature) or repeated empty output; timeout ~60–120s.
- **Specification Helper:** DLQ on malformed checklist/spec or repeated empty replies; timeout ~60s.
- **Lint/Sim/Distill workers:** DLQ on missing files or tool invocation errors that are not transient; retry once for transient tool failures; timeout per tool budget.

Retries vs DLQ should be enforced consistently: one retry for transient issues, otherwise NACK with `requeue=false` to allow DLX/DLQ quarantine.
