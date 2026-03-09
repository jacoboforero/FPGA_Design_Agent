# Orchestrator Component

The orchestrator is the runtime coordinator. It does not generate RTL or run tools directly; it schedules work and advances node state based on task results.

## Responsibilities
- Load design context and DAG.
- Start only nodes whose dependencies have succeeded.
- Publish stage tasks with run-scoped routing metadata.
- Consume results and advance state.
- Persist stage outputs to task memory and mirror them into run observability artifacts.
- Apply retry/failure policy and propagate dependency failures.

## Stage Orchestration Behavior
- Initial stage: implementation.
- Verification stages: lint -> testbench -> TB lint -> simulation -> acceptance.
- Failure-loop stages: distill -> reflect -> debug (with bounded retries).
- Debug retry budgets are tracked per reason (`rtl_lint`, `tb_lint`, `sim`).

## Attempt History And Stagnation
The orchestrator records compact attempt history for each node and can pass:
- prior failure signatures,
- touched files,
- patch summaries,
- repeated-failure (stuck) context
into reflection/debug tasks.

## Failure Propagation
If a node is marked `FAILED`, pending dependent nodes are transitively marked `FAILED` and never started.

## Related Code
- `orchestrator/orchestrator_service.py`
- `orchestrator/state_machine.py`
- `orchestrator/context_builder.py`
- `orchestrator/task_memory.py`
