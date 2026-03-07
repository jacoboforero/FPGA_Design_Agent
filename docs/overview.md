# Overview

## Purpose
Explain the end-to-end lifecycle at a high level (plan, execute, decide).

## Audience
New contributors and reviewers who need system context before code-level docs.

## Scope
Conceptual flow only. Detailed routing, contracts, and command syntax are covered elsewhere.

## Lifecycle
- **Plan**: Human + Spec Helper converge on L1-L5, then planner writes `artifacts/generated/design_context.json` and `artifacts/generated/dag.json`.
- **Execute**: Orchestrator advances nodes through implementation and verification stages. On simulation or lint failures, it can trigger distill/reflect/debug and retry (bounded by policy).
- **Decide**: Review generated artifacts, logs, and acceptance output for pass/fail decisions.

## Current Execution Shape
- Primary path: `PENDING -> IMPLEMENTING -> LINTING -> TESTBENCHING -> TB_LINTING -> SIMULATING -> ACCEPTING -> DONE`.
- Failure paths may include `DISTILLING -> REFLECTING -> DEBUGGING` before retrying lint/simulation.
- Dependency failures propagate to dependents as `FAILED`.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/state_machine.py`
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/orchestrator_service.py`

## Related Docs
- [architecture.md](./architecture.md)
- [workflows/failure-repair-loop.md](./workflows/failure-repair-loop.md)
- [spec-and-planning.md](./spec-and-planning.md)
