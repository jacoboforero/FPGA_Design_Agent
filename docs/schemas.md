# Schemas

## Purpose
Summarize shared message contracts and controlled vocabularies used across runtime components.

## Audience
Contributors changing task payloads, result payloads, routing enums, or validation behavior.

## Scope
Schema overview and usage guidance. Full model definitions remain in code.

## Core Contracts
- **TaskMessage**: task identity, routing fields, and execution context.
- **ResultMessage**: task completion status, logs, and optional analysis artifacts.

## Controlled Vocabularies
- `EntityType`: `REASONING`, `LIGHT_DETERMINISTIC`, `HEAVY_DETERMINISTIC`
- `AgentType`: planner/spec helper/implementation/testbench/reflection/debug
- `WorkerType`: linter/testbench linter/acceptance/simulator/distillation
- `TaskStatus`: `SUCCESS`, `FAILURE`, `ESCALATED_TO_HUMAN`

## Validation Guidance
- Validate payloads before execution.
- Preserve `task_id` and `correlation_id` across retries/results.
- Keep schema changes backward compatible unless coordinated as breaking changes.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/contracts.py`
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/specifications.py`
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/SCHEMAS.md`

## Related Docs
- [queues-and-workers.md](./queues-and-workers.md)
- [spec-and-planning.md](./spec-and-planning.md)
- [reference/runtime-config.md](./reference/runtime-config.md)
