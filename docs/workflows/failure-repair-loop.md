# Failure Repair Loop Workflow

## Purpose
Document bounded retry behavior used after verification failures.

## Audience
Engineers debugging orchestrator retry decisions and stage transitions.

## Scope
Failure-loop transitions and stop conditions.

## Loop Shape
- Simulation failure may trigger: `DISTILLING -> REFLECTING -> DEBUGGING -> retry`.
- Lint/TB-lint failures may trigger direct `DEBUGGING -> retry`.
- Retry count is bounded by runtime policy.

## Stop Conditions
- No meaningful code delta from debug patch.
- Retry limit reached for failure class.
- Non-recoverable stage failure.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/orchestrator_service.py`
- `/home/jacobo/school/FPGA_Design_Agent/core/runtime/config.py`

## Related Docs
- [../overview.md](../overview.md)
- [../components/orchestrator.md](../components/orchestrator.md)
