# Artifact Hygiene Workflow

Last verified against runtime behavior: March 8, 2026.

Use this workflow to keep historical run artifacts searchable and analyzable without deleting raw outputs.

## What This Page Is For
Use this page when you need to turn a growing artifact tree into a navigable campaign/run index.

## What This Page Is Not For
- It is not a replacement for observability layout docs. Use [observability.md](../observability.md).
- It is not a benchmark execution runbook. Use [benchmark-run.md](./benchmark-run.md).

## What It Generates
- canonical index files under `artifacts/index/`
- optional symlinked organized view under `artifacts/organized/`
- campaign grouping inferred from run/folder naming

## Run The Indexer
From repo root:

```bash
python3 scripts/index_runs.py --build-links
```

Optional flags:
- `--repo-root <path>`
- `--artifacts-root <path>`
- `--out-dir <path>`

## Main Index Outputs
- `artifacts/index/observability_runs.csv`
- `artifacts/index/benchmark_campaigns.csv`
- `artifacts/index/matrix_runs.csv`
- `artifacts/index/legacy_dirs.csv`
- `artifacts/index/campaign_summary.csv`
- `artifacts/index/summary.json`

`benchmark_campaigns.csv` includes per-mode benchmark entries with fields such as:
- `campaign_dir`, `run_id`, `mode`
- `model`, `provider`, `preset`, `status`
- `pass_rate`, `pass_count`, `sample_count`
- `manifest_path`, `run_root` (run directory)

## Which CSV To Open First

### Need to find broken or incomplete runtime executions
Start with:
1. `observability_runs.csv`
2. `campaign_summary.csv`

### Need benchmark campaign-level comparison inventory
Start with:
1. `benchmark_campaigns.csv`
2. `campaign_summary.csv`

### Need matrix sweep outcomes
Start with:
1. `matrix_runs.csv`

### Need cleanup/archive candidates
Start with:
1. `legacy_dirs.csv`

## Recommended Routine
1. Rebuild index after each campaign.
2. Review `campaign_summary.csv` for sanity.
3. Use `observability_runs.csv` to find incomplete runs.
4. Use `benchmark_campaigns.csv` to verify campaign/run/mode metadata integrity.
5. Use `legacy_dirs.csv` to decide archive/cleanup priorities.
6. Browse grouped outputs via `artifacts/organized/`.

## Related Code
- `scripts/index_runs.py`
- `docs/observability.md`
