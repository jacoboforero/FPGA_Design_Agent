# Testing plan

Cover contracts first, then the orchestration flow. Keep fast tests default; gate tool/LLM runs behind opt-in jobs.

## Unit / schema
- `tests/core/schemas`: enums, Task/Result validation, any agent-specific payloads.

## Integration (broker + workers)
- Happy path: implementation → lint → testbench → simulation → distill → reflect; assert states and artifacts/logs exist.
- Failure: missing file → DLQ, schema mismatch → DLQ, transient tool error → one retry then DLQ.
- Timeout: long sim triggers timeout → failure and no downstream tasks.
- Ordering: verify orchestrator issues tasks in the defined sequence and marks DONE/FAILED correctly.

## Workers
- Lint: Verilator on good/bad fixtures; expect exit code + logs.
- Simulation: iverilog/vvp on simple RTL/TB; expect exit code + stdout/stderr captured.
- Distill: sample sim log/waveform → distilled JSON path.

## Agents
- LLM off: tasks should fail with explicit errors (no fallback artifacts).
- LLM on (optional job): small prompts per agent; non-empty outputs and interface adherence.

## DLQ / retry
- Malformed task → NACK (requeue=false) → DLQ.
- Transient tool/LLM error → one retry → DLQ on repeat failure.
- Interface mismatch → DLQ and no further tasks for that node.

## CI knobs
- Default CI: schema + lightweight integration checks.
- Optional jobs: real Verilator/sim and LLM provider tests when secrets/tooling are available.
