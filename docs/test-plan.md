# Testing Plan (Outline)

Goal: cover schemas, orchestration flow, workers, and DLQ handling with fast tests; gate real tools/LLMs behind optional jobs.

## Unit/Schema
- `tests/core/schemas`: keep validating Task/Result/controlled vocabularies; add agent-specific payload validators if extended.

## Integration (broker + workers)
- Happy path: implementation → lint → testbench → simulation → distill → reflect; assert state transitions and artifact/log presence.
- Failure paths: missing files → DLQ, schema mismatch → DLQ, transient tool error → one retry then DLQ.
- Timeout path: long-running sim triggers timeout and failure handling.
- Orchestrator sequencing: ensure tasks are issued in defined order; retries do not duplicate artifacts; verify final `DONE`/`FAILED` states.

## Workers (tooling)
- Lint worker: run Verilator on good/bad fixtures; assert success/failure logs and artifacts.
- Simulation worker: run iverilog/vvp on simple RTL/TB; assert exit code, capture stdout/stderr, and optional coverage artifacts.
- Distill worker: feed sample sim log/waveform; assert distilled JSON written.

## Agents (LLM-backed)
- With LLM off: ensure fallbacks produce minimal artifacts/logs.
- With LLM on (optional job): smoke tests per agent using small prompts; assert non-empty outputs and interface adherence.

## DLQ/Retry
- Publish malformed task; assert NACK→DLQ.
- Publish transient-error task; assert one retry then DLQ on repeat failure.
- Publish interface-mismatched task; ensure DLQ and no downstream tasks issued.

## CI Notes
- Default CI: run schema + integration with mocked tools/LLMs; use lightweight fixtures.
- Optional jobs: enable real Verilator/sim and LLM provider tests with secrets in CI env.
