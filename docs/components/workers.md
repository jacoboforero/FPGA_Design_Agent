# Worker Components

## Purpose
Describe deterministic worker stages and expected outputs.

## Audience
Engineers maintaining lint/sim/acceptance/distillation execution paths.

## Scope
Worker-level behavior and result reporting expectations.

## Worker Set
- Lint worker (RTL checks)
- Testbench lint worker
- Simulation worker
- Acceptance worker
- Distillation worker

## Output Expectations
- Emit `ResultMessage` with explicit status and concise log output.
- Include artifact paths when files are produced.
- Preserve task identifiers from incoming task payload.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/workers/`
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/contracts.py`

## Related Docs
- [../queues-and-workers.md](../queues-and-workers.md)
- [../test-plan.md](../test-plan.md)
