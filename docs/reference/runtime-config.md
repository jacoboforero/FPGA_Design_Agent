# Runtime Config Reference

Last verified against runtime behavior: March 8, 2026.

Runtime config is loaded from YAML (default: `config/runtime.yaml`) and can be overridden by `--config` and `--preset`.

## What This Page Is For
Use this page to identify which runtime keys materially change behavior for engineer runs and benchmark runs.

## What This Page Is Not For
- It is not a complete schema dump for every key.
- It is not a command runbook; use workflow pages for command sequences.

## High-Impact Sections
- `active_preset`, `presets`: behavior profiles.
- `broker`: routing and queue interaction settings.
- `workers`: pool sizes.
- `llm`: provider/model and generation defaults.
- `tools`: external executable path overrides.
- `lint`, `sim`, `debug`: stage policy and thresholds.
- `benchmark`: benchmark paths and sampling settings.

## Typical Invocation
```bash
PYTHONPATH=. python3 apps/cli/cli.py --config config/runtime.yaml --preset engineer_fast
```

## Preset Guidance
- Use `engineer_fast` for rapid iteration during active design development.
- Use `engineer_signoff` when you want stricter verification posture before handoff.
- Use `benchmark` for benchmark-mode execution and researcher workflows.

## Benchmark Defaults (Common)
- `benchmark.verilog_eval_root`: `third_party/verilog-eval`
- `benchmark.prompts_dir`: `third_party/verilog-eval/dataset_spec-to-rtl`
- `benchmark.output_root`: `artifacts/benchmarks/verilog_eval`
- `benchmark.oracle_manifest`: optional JSON mapping for custom `test_sv`/`ref_sv`.
- `benchmark.canonical`: default canonical sampling profile (`n`, `temperature`, `top_p`).
- `benchmark.sampled`: default sampled profile (`n`, `temperature`, `top_p`).
- `benchmark.sim_run_timeout_s`: simulation timeout used in benchmark-mode simulation worker.
- `benchmark.near_miss_extra_retry_enabled`: allow near-miss simulation failures to receive extra debug retries.
- `benchmark.near_miss_max_mismatches`: mismatch threshold for near-miss classification.
- `benchmark.near_miss_extra_debug_retries`: extra retries granted for near-miss cases.

## Benchmark CLI Interaction
- `benchmark run` reads benchmark paths/profiles from this section unless overridden by CLI flags.
- `benchmark run --output-root` overrides `benchmark.output_root` for that invocation.
- Run artifacts are written to `<output_root>/<campaign>/<run_id>/...` by default.
- `benchmark analyze` consumes an existing mode directory containing official summary artifacts.

## Practical Configuration Hygiene
1. Keep team-shared behavior in YAML (`config/runtime*.yaml` variants).
2. Keep secrets (API keys, tokens) in environment variables, not YAML.
3. Use explicit presets in commands and campaign files for reproducibility.
4. Record run identity with meaningful campaign/run IDs in benchmark workflows.

## Related Code
- `config/runtime.yaml`
- `core/runtime/config.py`
