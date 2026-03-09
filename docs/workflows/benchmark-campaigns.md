# Benchmark Campaign Authoring

Last verified against runtime behavior: March 8, 2026.

This page explains how to define and run multi-entry benchmark campaigns with `scripts/run_benchmark_campaign.py`.

## What This Page Is For
Use this page when you want repeatable, scriptable campaign execution across multiple benchmark run entries.

## What This Page Is Not For
- It is not a replacement for benchmark run semantics; use [benchmark-run.md](./benchmark-run.md) for command behavior and outputs.
- It is not a benchmark-metrics interpretation guide; use [benchmark-methodology.md](../benchmark-methodology.md) for analysis guidance.

## Why Use Campaign Files
Campaign files give you:
- explicit run definitions in version-controllable YAML,
- repeatable command generation for model/config sweeps,
- a campaign-level execution report (`campaign_report.json`).

## Campaign Runner Command

```bash
python3 scripts/run_benchmark_campaign.py --campaign-file benchmarks/verilog_eval/campaign.example.yaml
```

Useful runner flags:
- `--dry-run`: print generated commands without executing.
- `--continue-on-error`: continue later entries if one run fails.
- `--report-out <path>`: custom campaign report path.

## Campaign File Schema
Top-level keys:
- `campaign` (string): campaign name. Used in run path layout and reporting.
- `output_root` (string, optional): default benchmark output root for runs.
- `runs` (required list): ordered run entries.

Each `runs[]` entry supports:
- `label` (string): human-readable run label (also default run-id token).
- `config` (string): runtime YAML path passed to benchmark CLI.
- `preset` (string): runtime preset (typically `benchmark`).
- `sampled` (bool): enable sampled mode in addition to canonical.
- `legacy_lightweight` (bool): use compatibility generation path.
- `resume` (bool): resume an existing run directory.
- `overwrite` (bool): replace an existing run directory.
- `purge_queues` (bool): optional queue purge (unsafe in shared environments).
- `pipeline_timeout` (number): benchmark per-sample timeout override.
- `max_problems` (int): limit discovery set for run.
- `only_problem` (string or list): restrict run to specific problem IDs.
- `run_id` (string): explicit run ID override.
- `run_dir` (string): explicit run directory override.
- `output_root` (string): per-entry output root override.
- `extra_args` (list): additional CLI args appended verbatim.

## Defaults and Resolution Rules
- `campaign` defaults to campaign file stem if omitted.
- `run_id` defaults to slugified `label` if omitted.
- entry `output_root` overrides top-level `output_root`.
- entry `run_dir` overrides campaign/output-root/run-id layout.
- if `only_problem` is a string, it is treated as a single-item list.

## Example: Baseline + Sampled Pair

```yaml
campaign: gpt41_smoke
output_root: artifacts/benchmarks/verilog_eval
runs:
  - label: gpt41_canonical
    config: config/runtime.yaml
    preset: benchmark
    sampled: false
    max_problems: 10
  - label: gpt41_sampled
    config: config/runtime.yaml
    preset: benchmark
    sampled: true
    max_problems: 10
```

## Example: Targeted Reproduction Run

```yaml
campaign: bug_repro
output_root: artifacts/benchmarks/verilog_eval
runs:
  - label: repro_prob079
    config: config/runtime.yaml
    preset: benchmark
    only_problem: Prob079
    pipeline_timeout: 240
    resume: true
```

## Example: Shared Environment Safe Pattern
In shared broker environments, avoid queue purges and prefer explicit run IDs.

```yaml
campaign: shared_lab_sweep
output_root: artifacts/benchmarks/verilog_eval
runs:
  - label: model_a_round1
    run_id: model_a_round1
    config: config/runtime.yaml
    preset: benchmark
    sampled: false
    purge_queues: false
  - label: model_b_round1
    run_id: model_b_round1
    config: config/runtime.yaml
    preset: benchmark
    sampled: false
    purge_queues: false
```

## Campaign Report Output
After execution, the runner writes `campaign_report.json` containing:
- campaign metadata (`campaign`, `campaign_file`, timestamps),
- each run entry’s generated command,
- resolved run directory path,
- status and return code per entry,
- failure count and run count summary.

This report is intended for auditability and scripted post-processing.

## Common Authoring Pitfalls

### Pitfall: missing `runs` key
Symptom:
- runner exits with campaign schema error.

Fix:
- ensure top-level `runs` exists and is a non-empty list.

### Pitfall: accidental output overlap across entries
Symptom:
- entries collide on same run directory and trigger overwrite/resume behavior unexpectedly.

Fix:
- set explicit unique `run_id` values for each entry.
- avoid mixing `run_dir` with overlapping paths unless intentional.

### Pitfall: ambiguous run intent in reports
Symptom:
- difficult to interpret campaign output later.

Fix:
- use descriptive `campaign` and `label` values that encode model/config intent.

## How This Fits Into the Research Workflow
Recommended order:
1. Author campaign YAML and validate with `--dry-run`.
2. Execute campaign.
3. Inspect per-run `run_manifest.json` and mode `aggregate.json` files.
4. Run `benchmark compare` for key pairwise comparisons.
5. Rebuild index with `python3 scripts/index_runs.py --build-links`.

## Related Code
- `scripts/run_benchmark_campaign.py`
- `benchmarks/verilog_eval/campaign.example.yaml`
- `apps/cli/run_verilog_eval.py`
