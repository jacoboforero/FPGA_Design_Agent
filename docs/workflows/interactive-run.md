# Interactive Run Workflow

Last verified against runtime behavior: March 8, 2026.

This is the fastest way to run the full planning and execution loop locally.

This workflow is designed for hardware engineers building and iterating on real designs.

## What This Page Is For
Use this page when you want to go from a design idea to generated RTL and execution artifacts in one guided CLI session.

## What This Page Is Not For
- It is not the benchmark/research workflow. For that, use [benchmark-run.md](./benchmark-run.md).
- It is not a deep architecture reference. For internals, use [architecture.md](../architecture.md).

## Success Criteria
A successful engineer run means all of the following are true:
1. You completed spec collection (interactive or from file).
2. Planner produced `design_context.json` and `dag.json`.
3. You passed the execution handoff prompt (`Proceed to execution?`) or ran with `--yes`.
4. The orchestrator completed execution and emitted generated RTL artifacts.
5. You can inspect run outputs under generated, task-memory, and observability directories.

## Fastest Path (15-Minute Engineer First Success)
Containerized path (recommended):

```bash
make build
make up
make deps
make cli
```

Host fallback:

```bash
PYTHONPATH=. python3 apps/cli/cli.py --timeout 120 --config config/runtime.yaml --preset engineer_fast
```

If you only want to validate environment readiness before running the full pipeline:

```bash
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset engineer_fast
```

## End-to-End Flow
1. Start CLI with your desired preset (`engineer_fast` for iteration speed, `engineer_signoff` for stricter verification policy).
2. Provide spec intent in the interactive helper flow.
3. Complete/fix required L1-L5 fields if prompted.
4. Planner emits design context and DAG artifacts.
5. CLI presents execution handoff prompt.
6. Orchestrator runs implementation and verification stages.
7. Review generated RTL and supporting artifacts.
8. Iterate on spec/config and rerun.

## Expected Checkpoints
These checkpoints reduce guesswork and help you quickly detect where a run drifted.

### Checkpoint 1: Spec Collection Active
What you should observe:
- CLI is prompting for module intent/signals/behavior or reading from provided spec file.
- `artifacts/task_memory/specs/` starts filling with spec JSON artifacts.

Sanity checks:
```bash
ls -1 artifacts/task_memory/specs
```

You should see files like:
- `L1_functional*.json`
- `L2_interface*.json`
- `L3_verification*.json`
- `L4_architecture*.json`
- `L5_acceptance*.json`
- `frozen_spec*.json`
- `lock.json`

### Checkpoint 2: Planner Completed
What you should observe:
- Planner phase completes without timeout/failure.
- DAG summary is printed in CLI output.

Sanity checks:
```bash
ls artifacts/generated/design_context.json artifacts/generated/dag.json
```

### Checkpoint 3: Execution Handoff Gate
What you should observe:
- CLI asks `Proceed to execution?` unless running with `--yes`.
- This is the intended human-in-the-loop control point.

### Checkpoint 4: Orchestrator and Workers Running
What you should observe:
- Stage progress through implementation and verification states.
- On failures, bounded repair stages may execute (`distill`, `reflect`, `debug`) based on policy.

### Checkpoint 5: Run Outputs Ready
What you should observe:
- Generated RTL files under `artifacts/generated/`.
- Stage logs and intermediate context under `artifacts/task_memory/`.
- Run-scoped telemetry under `artifacts/observability/runs/<run_name>/<run_id>/`.

## Artifacts To Inspect First
When the run succeeds, inspect in this order:
1. `artifacts/generated/` for primary outputs.
2. `artifacts/task_memory/` for stage-level diagnostics and context handoff artifacts.
3. `artifacts/observability/` for metrics, summary, and cost trail.

## Troubleshooting by Symptom
This section maps frequent symptoms to concrete next actions.

### Symptom: broker connectivity failures
Symptoms:
- CLI fails early with RabbitMQ connection errors.

Actions:
1. Run `PYTHONPATH=. python3 apps/cli/cli.py doctor --preset engineer_fast`.
2. Verify `broker.url` in `config/runtime.yaml`.
3. If running in Docker, confirm services are up (`make up`) and retry.

### Symptom: LLM credential/provider errors
Symptoms:
- Missing API key or provider authentication failures.

Actions:
1. Confirm provider in runtime config (`llm.provider`).
2. Export matching credential (`OPENAI_API_KEY` or `GROQ_API_KEY`).
3. Re-run `doctor` and verify credential check passes.

### Symptom: planner emits no `design_context.json`
Symptoms:
- Planner stage fails or exits without expected artifacts.

Actions:
1. Re-check spec completeness in `artifacts/task_memory/specs`.
2. Inspect planner-related logs in task-memory/observability artifacts.
3. Retry with a more explicit spec (especially interface details and verification intent).

### Symptom: execution fails after planner success
Symptoms:
- Planner succeeds but node execution stalls/fails.

Actions:
1. Inspect `artifacts/task_memory/` stage outputs for failing node/stage.
2. Review run summary under observability for failure stage and error context.
3. If lint/simulation-related, check worker tool dependencies via `doctor`.

### Symptom: repeated repair-loop retries with no progress
Symptoms:
- Distill/reflect/debug cycle repeats and exits exhausted.

Actions:
1. Inspect failing node logs and generated candidate diffs.
2. Tighten spec acceptance criteria or clarify corner cases.
3. Re-run with adjusted preset or debug retry policy if appropriate.

## Engineer Next Steps
After your first successful run:
1. Move to [spec-and-planning.md](../spec-and-planning.md) to improve spec quality and reduce downstream retries.
2. Use [failure-repair-loop.md](./failure-repair-loop.md) to understand retry behavior and stop conditions.
3. Use [observability.md](../observability.md) and [artifact-hygiene.md](./artifact-hygiene.md) to make runs searchable and comparable over time.

## Related Code
- `apps/cli/cli.py`
- `apps/cli/spec_flow.py`
- `orchestrator/orchestrator_service.py`
