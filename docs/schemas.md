# Message Schemas & Controlled Vocabularies

Shared schemas keep the Orchestrator, agents, and deterministic workers aligned. Full tables live in `schemas/SCHEMAS.md` and the source of truth models are in `schemas/contracts.py`.

## Core Models

- **TaskMessage:** Work unit published by the Orchestrator. Includes `task_id`, `correlation_id`, `priority`, routing fields (`entity_type`, `task_type` via `AgentType`/`WorkerType`), and a `context` payload with task-specific parameters.  
- **ResultMessage:** Completion record emitted by workers. Includes `status` (`TaskStatus`), `artifacts_path`, `log_output`, optional `metrics` (`CostMetrics`), and optional analysis payloads (`AnalysisMetadata`, `DistilledDataset`, `ReflectionInsights`).

## Controlled Vocabularies

- **EntityType:** `REASONING`, `LIGHT_DETERMINISTIC`, `HEAVY_DETERMINISTIC` (maps to routing/worker class).  
- **AgentType:** `SpecificationHelperAgent`, `PlannerAgent`, `ImplementationAgent`, `TestbenchAgent`, `ReflectionAgent`, `DebugAgent` (selected per agent task).  
- **WorkerType:** `LinterWorker`, `SimulatorWorker`, `SynthesizerWorker`, `DistillationWorker` (deterministic tasks).  
- **TaskPriority:** `LOW`, `MEDIUM`, `HIGH`.  
- **TaskStatus:** `SUCCESS`, `FAILURE`, `ESCALATED_TO_HUMAN`.

## Usage Notes

- Workers must validate inbound messages against these schemas before execution; schema failures should be rejected to the DLQ.  
- Orchestrator and workers should preserve `task_id` and `correlation_id` across retries to maintain traceability from planning artifacts to execution attempts.  
- Coverage identifiers, interface enums, and routing metadata referenced in L1–L5 planning artifacts should align with these schemas to avoid poison pills. See [queues-and-workers.md](./queues-and-workers.md) for DLX/DLQ handling.
