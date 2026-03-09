# Observability

Last verified against runtime behavior: March 8, 2026.

Each run emits execution telemetry, metrics, and cost logs under `artifacts/observability/`.

## What This Page Is For
Use this page to find run telemetry quickly and decide where to inspect first when runs fail or behave unexpectedly.

## What This Page Is Not For
- It is not a benchmark command runbook. Use [workflows/benchmark-run.md](./workflows/benchmark-run.md).
- It is not an artifact indexing tutorial. Use [workflows/artifact-hygiene.md](./workflows/artifact-hygiene.md).

## Per-Run Layout
- `artifacts/observability/runs/<run_name>/<run_id>/observability/events.jsonl`
- `artifacts/observability/runs/<run_name>/<run_id>/observability/execution_metrics.json`
- `artifacts/observability/runs/<run_name>/<run_id>/observability/summary.json`
- `artifacts/observability/runs/<run_name>/<run_id>/observability/costs.jsonl`
- `artifacts/observability/runs/<run_name>/<run_id>/task_memory/` (mirrored stage artifacts)

## Legacy Files and Aggregates
- Legacy mirror files may still appear in `artifacts/observability/` for compatibility.
- Global aggregates are written to `artifacts/observability/costs.jsonl` and `cost_summary.json`.

## What To Inspect First
Use this quick map to diagnose issues faster.

### Case A: run failed before planning/execution started
Inspect in order:
1. CLI output and doctor checks for environment/tooling issues.
2. `summary.json` in the run observability directory (if present).
3. Broker/tool credential checks in runtime config context.

### Case B: planner succeeded but execution failed
Inspect in order:
1. `events.jsonl` for stage transition timeline and failing stage context.
2. `task_memory/` mirrored artifacts for failing node/stage details.
3. `execution_metrics.json` to identify bottleneck stage and duration profile.

### Case C: benchmark run produced lower-than-expected pass rates
Inspect in order:
1. Benchmark mode `summary.csv` and `aggregate.json` for per-problem outcomes.
2. Problem sample logs (`*-sv-generate.log`, `*-sv-iv-test.log`).
3. Pipeline snapshots (`pipeline_sampleXX/`) for failing sample traces.
4. `run_manifest.json` to verify model/config/preset comparability.

### Case D: cost or token usage anomalies
Inspect in order:
1. run-scoped `costs.jsonl` and `execution_metrics.json`.
2. global aggregate `artifacts/observability/cost_summary.json`.
3. run labels/manifests to isolate campaigns or model changes.

## Run Indexing
Use `scripts/index_runs.py` to build:
- `artifacts/index/*.csv`
- `artifacts/index/summary.json`
- optional symlinked organization view in `artifacts/organized/`

## Related Code
- `core/observability/`
- `core/observability/run_artifacts.py`
- `scripts/index_runs.py`
- `apps/cli/cli.py`
