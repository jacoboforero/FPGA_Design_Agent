# Benchmark Methodology

Last verified against runtime behavior: March 8, 2026.

This project uses VerilogEval-compatible scoring and keeps official analyzer outputs as the final scoring record.

## What This Page Is For
Use this page to interpret benchmark outputs correctly and avoid invalid comparisons.

## What This Page Is Not For
- It is not a command runbook. For command usage, see [workflows/benchmark-run.md](./workflows/benchmark-run.md).
- It is not campaign YAML authoring guidance. For that, see [workflows/benchmark-campaigns.md](./workflows/benchmark-campaigns.md).

## Benchmark Execution Policy
- Default benchmark mode uses the orchestrated pipeline (planning + orchestrator + workers).
- Benchmark mode binds benchmark-provided oracle testbench/reference assets.
- Generation failures are recorded per sample and the run continues so official analysis can still complete.
- Official analyzer output (`summary.txt`, `summary.csv`) determines benchmark pass-rate metrics.
- Queue purging is optional (`--purge-queues`) to avoid disrupting shared environments.

## Profiles
- **Canonical**: deterministic/low-variance settings (default `n=1`).
- **Sampled**: higher-variance multi-sample settings (config-driven `n`, temperature, top_p).

## Official Scoring and Supporting Artifacts
### Official scoring artifacts
- `summary.txt`
- `summary.csv`

### Supporting artifacts for reproducibility and automation
- `aggregate.json` (structured convenience summary parsed from official outputs)
- `run_manifest.json` (run metadata: config, model/provider, flags, filters, timestamps)

Interpretation rule:
- Treat official artifacts as the final scoring record.
- Use aggregate/manifest artifacts for analysis automation and reproducibility tracing.

## Compare Semantics
`benchmark compare` reports left/right metrics and deltas.

Recommended practice:
1. Compare matching mode directories (`canonical` vs `canonical`, `sampled` vs `sampled`).
2. Keep problem set identical (`max-problems`/`only-problem` filters should match).
3. Keep run policy comparable (queue-purge behavior, timeout policy, legacy/orchestrated mode).
4. Verify both runs have complete official outputs before interpreting deltas.

## Interpreting Pass-Rate Deltas Responsibly
When reading `pass_rate` deltas:
- A positive delta indicates right run outperformed left run for the compared mode/problem set.
- A negative delta indicates regression.
- Small deltas on tiny subsets are weak evidence; use larger or full sets for stronger claims.

Checklist before making model-quality claims:
1. Same benchmark mode (`canonical` or `sampled`).
2. Same problem universe and filters.
3. Same toolchain/runtime environment where possible.
4. No partial/incomplete runs mistaken as full results.
5. Per-problem rows inspected for concentrated failure clusters.

## Failure Interpretation Guidance
- If `summary` artifacts exist but pass-rate is lower than expected, inspect per-problem `npass/nsamples` and failure markers first.
- If many failures cluster in a small set of problems, treat as targeted weakness rather than global model quality signal.
- If generation warnings are frequent but run completes, inspect `*-sv-generate.log`, `*-sv-iv-test.log`, and pipeline snapshots to separate model weakness from runtime/tooling instability.

## Recommended Analysis Workflow
1. Run campaign(s) with explicit run identity (`campaign`, `run_id`).
2. Validate run completeness via mode-level official artifacts.
3. Run pairwise `benchmark compare` for candidate configurations.
4. Review per-problem rows for dominant failure modes.
5. Re-run targeted subsets with `--only-problem` to reproduce critical regressions.
6. Rebuild artifact index for cross-campaign navigation.

## Related Code
- `apps/cli/run_verilog_eval.py`
- `scripts/run_benchmark_campaign.py`
- `tests/apps/test_run_verilog_eval.py`
- `tests/apps/test_run_benchmark_campaign.py`
- `config/runtime.yaml`
