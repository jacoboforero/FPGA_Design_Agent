# Worker Components

Deterministic workers run tool-backed checks and transformations. They do not perform LLM reasoning.

## Worker Set
- **Lint worker**: RTL linting and semantic checks.
- **Testbench lint worker**: TB compile/lint validation.
- **Simulation worker**: compile and execute simulation.
- **Acceptance worker**: evaluate acceptance gate conditions.
- **Distillation worker**: distill failure logs/waveform context into a compact dataset.

## Expected Result Behavior
Each worker should publish a `ResultMessage` with:
- `task_id` and `correlation_id` from input task,
- explicit `status`,
- useful `log_output`,
- `artifacts_path` when files are produced.

## Failure Handling
- Missing/invalid required task input is treated as hard input failure.
- Transient infrastructure/tool errors can use retry policy.
- Unrecoverable failures should dead-letter by queue policy.

## Related Code
- `workers/lint/worker.py`
- `workers/tb_lint/worker.py`
- `workers/sim/worker.py`
- `workers/acceptance/worker.py`
- `workers/distill/worker.py`
- `core/schemas/contracts.py`
