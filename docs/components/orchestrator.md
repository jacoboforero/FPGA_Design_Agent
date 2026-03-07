# Orchestrator Component

## Purpose
Detail orchestrator responsibilities, transitions, and result-handling behavior.

## Audience
Engineers modifying orchestration logic or diagnosing pipeline ordering issues.

## Scope
Runtime orchestration internals per run.

## Responsibilities
- Start ready nodes based on dependency completion.
- Publish stage tasks and correlate incoming results.
- Maintain per-node state and failure propagation.
- Trigger repair loop stages when configured.

## Key Behaviors
- Dependency closure failure propagation to blocked nodes.
- Run-scoped result routing key handling.
- Attempt tracking and bounded retry policy.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/orchestrator_service.py`
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/state_machine.py`
- `/home/jacobo/school/FPGA_Design_Agent/orchestrator/context_builder.py`

## Related Docs
- [../architecture.md](../architecture.md)
- [../workflows/failure-repair-loop.md](../workflows/failure-repair-loop.md)
