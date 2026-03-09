# Schemas

Schema contracts define how orchestrator, agents, and workers communicate.

## Core Messages
- **`TaskMessage`**: unit of work dispatched for a node/stage.
- **`ResultMessage`**: completion payload with status, logs, and optional artifacts.

## Key Enums
- **`EntityType`**: `REASONING`, `LIGHT_DETERMINISTIC`, `HEAVY_DETERMINISTIC`
- **`AgentType`**: planner, implementation, testbench, reflection, debug, spec helper
- **`WorkerType`**: linter, tb linter, simulator, acceptance, distillation
- **`TaskStatus`**: `SUCCESS`, `FAILURE`, `ESCALATED_TO_HUMAN`

## Practical Notes
- Preserve `task_id` and `correlation_id` through execution and result publication.
- `ESCALATED_TO_HUMAN` exists in schema; most current runtime flows use success/failure transitions.
- Keep backwards compatibility in message shape when possible; coordinate breaking changes with orchestrator and workers together.

## Planning Schemas
L1-L5 planning artifacts are modeled in `core/schemas/specifications.py`, including frozen-state checks and cross-document consistency.

## Related Code
- `core/schemas/contracts.py`
- `core/schemas/specifications.py`
- `core/schemas/SCHEMAS.md`
