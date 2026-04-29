# Benchmark Methodology

Last verified against runtime behavior: March 15, 2026.

This project uses VerilogEval v2-compatible scoring and keeps official analyzer outputs as the final scoring record.

## What This Page Is For
Use this page to interpret benchmark outputs correctly and avoid invalid comparisons.

## Benchmark Family

The repository vendors NVIDIA's VerilogEval benchmark as a git submodule at
`third_party/verilog-eval`. The current checked-out submodule revision is tagged
`v2.0.0`.

VerilogEval v2 is the right benchmark family for this project because it tests
specification-to-RTL generation with functional checks, not only code
completion. It is also the benchmark family commonly cited by public AI-for-EDA
agent systems, so it gives this repo a recognizable evaluation surface.

Do not compare a local result to another published number unless the comparison
matches the problem set, model/provider, prompt policy, sample count,
temperature/top-p, tool versions, and run flow. This repo records those details
in `run_manifest.json` so full-set results can be interpreted later.

## What This Page Is Not For
- It is not a command runbook. For command usage, see [workflows/benchmark-run.md](./workflows/benchmark-run.md).
- It is not campaign YAML authoring guidance. For that, see [workflows/benchmark-campaigns.md](./workflows/benchmark-campaigns.md).

## Benchmark Execution Policy
- Default benchmark mode uses `direct_single_module`, which creates a one-node design context directly from the benchmark prompt and then runs the orchestrator/worker pipeline on that direct context.
- `orchestrated` remains available for planner/path ablations and multi-stage benchmark experiments.
- `--legacy-lightweight` remains available as a compatibility baseline that bypasses the worker pipeline.
- Benchmark mode binds benchmark-provided oracle testbench/reference assets.
- Benchmark mode preserves the raw benchmark prompt by default.
- Generation failures are recorded per sample and the run continues so official analysis can still complete.
- Official analyzer output (`summary.txt`, `summary.csv`) determines benchmark pass-rate metrics.
- Queue purging is optional (`--purge-queues`) to avoid disrupting shared environments.

## Profiles
- **Canonical**: deterministic/low-variance settings (default `n=1`).
- **Sampled**: higher-variance multi-sample settings (config-driven `n`, temperature, top_p).

## Frontier-Model Campaign Guidance

For a shareable full-set run, use a named campaign and run id, and keep the
manifest with the final report:

```bash
make build
make up
make deps
make shell
git submodule update --init --recursive
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run \
  --config config/runtime.benchmark.yaml \
  --campaign frontier_verilogeval_v2 \
  --run-id gpt41_canonical_full \
  --max-problems 0 \
  --pipeline-timeout 240
```

Use `--dry-run` first when changing provider/model settings. Only publish a run
after confirming the manifest names the intended model and the canonical
directory contains official `summary.txt` and `summary.csv` outputs.

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
3. Keep run policy comparable (`flow_mode`, `prompt_mode`, `rtl_language`, queue-purge behavior, timeout policy, legacy/direct/orchestrated mode).
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
- `config/runtime.benchmark.yaml`
