# Specification and Planning

## Purpose
Define how L1-L5 specs are produced, frozen, and transformed into execution artifacts.

## Audience
Contributors authoring specs, planner behavior, or design-context generation.

## Scope
Planning and handoff contracts only. Execution runtime details are covered elsewhere.

## Workflow
1. Collect and refine L1-L5 spec layers.
2. Lock specs under `artifacts/task_memory/specs/`.
3. Planner emits `artifacts/generated/design_context.json` and `artifacts/generated/dag.json`.

## L1-L5 Summary
- **L1** functional intent
- **L2** interface contract
- **L3** verification objectives
- **L4** architecture and dependencies
- **L5** acceptance criteria

## Multi-Module Notes
- Use repeated `Module: <name>` sections.
- Optional `Top: <module>` selects top module.
- Planner maps dependency edges and emits node/dependency structure in DAG.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/spec_flow.py`
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/planner.py`

## Related Docs
- [overview.md](./overview.md)
- [architecture.md](./architecture.md)
- [schemas.md](./schemas.md)
