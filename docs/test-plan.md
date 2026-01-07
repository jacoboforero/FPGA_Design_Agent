# Testing Plan (Outline)

Goal: cover schemas, orchestration flow, workers, and DLQ handling with fast tests; gate real tools/LLMs behind optional jobs.

## Unit/Schema
- `tests/core/schemas`: keep validating Task/Result/controlled vocabularies; add agent-specific payload validators if extended.

## Integration (broker + workers)
- Happy path: implementation → lint → testbench → simulation → distill → reflect; assert state transitions and artifact/log presence.
- Failure paths: missing files → DLQ, schema mismatch → DLQ, transient tool error → one retry then DLQ.
- Timeout path: long-running sim triggers timeout and failure handling.

## Workers (tooling)
- Lint worker: run Verilator on good/bad fixtures; assert success/failure logs and artifacts.
- Simulation worker: stub or real sim on simple RTL; assert exit code, coverage/log capture.
- Distill worker: feed sample sim log/waveform; assert distilled JSON written.

## Agents (LLM-backed)
- With LLM off: ensure fallbacks produce minimal artifacts/logs.
- With LLM on (optional job): smoke tests per agent using small prompts; assert non-empty outputs and interface adherence.

## DLQ/Retry
- Publish malformed task; assert NACK→DLQ.
- Publish transient-error task; assert one retry then DLQ on repeat failure.

## CI Notes
- Default CI: run schema + integration with mocked tools/LLMs; use lightweight fixtures.
- Optional jobs: enable real Verilator/sim and LLM provider tests with secrets in CI env.
