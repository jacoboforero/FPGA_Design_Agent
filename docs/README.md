# Documentation Index

## Purpose
Provide a master map for project documentation and prevent drift across component, workflow, and reference docs.

## Audience
Contributors, maintainers, and reviewers working on the pipeline.

## Scope
Index only. This file links to canonical docs; it does not restate implementation rules.

## Root Guides
- `overview.md` (purpose: system lifecycle)
- `architecture.md` (purpose: component map and state progression)
- `agents.md` (purpose: LLM agent responsibilities)
- `cli.md` (purpose: command-line usage)
- `spec-and-planning.md` (purpose: L1-L5 planning workflow)
- `queues-and-workers.md` (purpose: broker and worker routing)
- `schemas.md` (purpose: message contracts and enums)
- `test-plan.md` (purpose: test strategy and commands)
- `observability.md` (purpose: runtime events and cost tracking)
- `benchmark-methodology.md` (purpose: benchmark scoring policy)
- `config-migration.md` (purpose: env-to-YAML runtime migration)

## Component Docs (`docs/components/`)
- `components/orchestrator.md` (purpose: orchestration loop and transitions)
- `components/workers.md` (purpose: deterministic worker behavior)
- `components/llm-gateway.md` (purpose: provider gateway and model selection)
- `components/ui-bridge.md` (purpose: FastAPI bridge for VS Code extension)

## Workflow Docs (`docs/workflows/`)
- `workflows/interactive-run.md` (purpose: interactive full-run flow)
- `workflows/benchmark-run.md` (purpose: benchmark runbook)
- `workflows/failure-repair-loop.md` (purpose: debug retry lifecycle)

## Reference Docs (`docs/reference/`)
- `reference/runtime-config.md` (purpose: runtime YAML field reference)
- `reference/test-commands.md` (purpose: command quick reference)

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/README.md`
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/cli.py`

## Related Docs
- [overview.md](./overview.md)
- [architecture.md](./architecture.md)
