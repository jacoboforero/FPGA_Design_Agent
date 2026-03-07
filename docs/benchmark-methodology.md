# Benchmark Methodology

## Purpose
Define benchmark execution and scoring policy for VerilogEval-compatible runs.

## Audience
Engineers running or reviewing benchmark results.

## Scope
Benchmark flow, profiles, and artifact expectations.

## Execution Policy
- Default benchmark mode exercises the orchestrated pipeline (planner phase + queue-backed workers + orchestrator state machine).
- Benchmark policy enforces repair-loop enabled behavior.
- Runs are fail-fast: first orchestrated sample pipeline failure aborts the run.
- Official VerilogEval scoring (`sv-iv-analyze`) remains the source for `summary.txt` / `summary.csv`.

## Profiles
- Canonical: `n=1`, low-temperature deterministic setting
- Sampled: configurable multi-sample setting

## Execution (from repo root)
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --sampled
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --legacy-lightweight
```

## Expected Outputs
- Official-style benchmark summaries
- Sample-level compile/run logs
- Per-sample pipeline traces under `pipeline_sampleXX/`
- Internal aggregate report derived from benchmark outputs

## Source of Truth
- `apps/cli/run_verilog_eval.py`
- `config/runtime.yaml`
- `third_party/verilog-eval/` (upstream harness + official `dataset_spec-to-rtl`)

## Related Docs
- [workflows/benchmark-run.md](./workflows/benchmark-run.md)
- [cli.md](./cli.md)
