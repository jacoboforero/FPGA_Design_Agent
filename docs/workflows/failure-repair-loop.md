# Failure Repair Loop Workflow

When verification fails, the orchestrator can trigger a bounded repair loop instead of failing immediately.

## Loop Shape
- Simulation failure path:
  - `SIMULATING -> DISTILLING -> REFLECTING -> DEBUGGING -> retry`
- Lint/TB-lint failure path:
  - `LINTING/TB_LINTING -> DEBUGGING -> retry`

## Retry And Stop Conditions
A node is failed when any of these happen:
- debug retries are exhausted for that failure reason,
- debug produces no meaningful code change,
- a non-recoverable stage fails,
- repair loop is disabled by policy.

## Debug Context Passed Between Attempts
The loop can pass attempt history and stagnation context into reflection/debug tasks so repeated failure signatures are handled with strategy changes.

## Related Code
- `orchestrator/orchestrator_service.py`
- `orchestrator/state_machine.py`
- `core/runtime/config.py`
