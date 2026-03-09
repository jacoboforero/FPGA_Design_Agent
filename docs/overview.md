# Overview

The project turns a hardware specification into generated RTL, verification artifacts, and execution evidence through a two-phase workflow.

For product goals and intended UX language, see [vision-and-ux.md](./vision-and-ux.md).

## What Happens In A Run
1. Write or load a design spec.
2. Complete and freeze L1-L5 planning artifacts.
3. Run planner to emit `artifacts/generated/design_context.json` and `artifacts/generated/dag.json`.
4. Confirm execution.
5. Orchestrator drives each DAG node through implementation and verification stages.
6. On failures, repair loop stages can run (`distill -> reflect -> debug`) and retry.
7. Outputs and traces are written under generated, task-memory, and observability artifact roots.

## Current Runtime State Progression
- Success path: `PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> TB_LINTING -> SIMULATING -> ACCEPTING -> DONE`
- Failure/repair path (when enabled): simulation or lint failures can route through `DISTILLING`, `REFLECTING`, and `DEBUGGING` before retry.
- Dependency-aware execution: nodes start only after dependencies reach `DONE`; failed dependencies can block dependents as `FAILED`.

## User Experience Summary
- Interactive mode is human-in-the-loop during planning.
- Execution is automated after the planning approval gate.
- You inspect artifacts and logs, then iterate on spec or config as needed.

## Related Code
- `apps/cli/cli.py`
- `apps/cli/spec_flow.py`
- `orchestrator/orchestrator_service.py`
- `orchestrator/state_machine.py`
