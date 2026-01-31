# Testing plan

Cover contracts first, then the orchestration flow. Keep fast tests default; gate tool/LLM runs behind opt-in jobs.

## Unit / schema
- `tests/core/schemas`: enums, Task/Result validation, any agent-specific payloads.

## Integration (broker + workers)
- Happy path: implementation → lint → testbench → TB lint → simulation → acceptance → DONE; assert states and artifacts/logs exist.
- Failure: missing file → DLQ, schema mismatch → DLQ, transient tool error → one retry then DLQ.
- Sim failure: distill → reflect → debug (patch) → re-run verification (bounded retries) → (DONE or FAILED); assert per-attempt logs/insights are persisted.
- TB lint failure: debug (patch) → retry verification (bounded retries); assert TB lint log + debug outputs exist.
- Acceptance failure: mark FAILED; assert acceptance log includes missing artifacts/metrics.
- Timeout: long sim triggers timeout → distill → reflect → debug → FAILED.
- Ordering: verify orchestrator issues tasks in the defined sequence and marks DONE/FAILED correctly.

## Workers
- RTL lint: Verilator on good/bad fixtures; expect exit code + logs.
- Testbench lint: iverilog -tnull on good/bad TBs; expect exit code + logs.
- Acceptance: required artifacts + metrics checks (coverage report/log parsing).
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
