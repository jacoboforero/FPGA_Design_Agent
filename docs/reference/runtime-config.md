# Runtime Config Reference

Last verified against runtime behavior: March 15, 2026.

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
PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml --preset engineer_fast
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
- `benchmark.flow_mode`: benchmark generation path selection.
- `benchmark.prompt_mode`: raw prompt preservation policy for worker context.
- `benchmark.disable_tb_generation`: skip generated TBs and rely on benchmark/public TB assets.
- `benchmark.debug_rtl_only`: restrict benchmark debug edits to RTL only.
- `benchmark.use_public_testbench`: bind benchmark-provided TB/reference assets into design context.
- `benchmark.interface_equivalence`: interface match policy for generated RTL versus benchmark target.
- `benchmark.rtl_language`: RTL language policy used in benchmark worker prompts/sanitization.
- `benchmark.canonical`: default canonical sampling profile (`n`, `temperature`, `top_p`).
- `benchmark.sampled`: default sampled profile (`n`, `temperature`, `top_p`).
- `benchmark.sim_run_timeout_s`: simulation timeout used in benchmark-mode simulation worker.
- `benchmark.near_miss_extra_retry_enabled`: allow near-miss simulation failures to receive extra debug retries.
- `benchmark.near_miss_max_mismatches`: mismatch threshold for near-miss classification.
- `benchmark.near_miss_extra_debug_retries`: extra retries granted for near-miss cases.

## Benchmark Flow Controls
- `benchmark.flow_mode`
  `direct_single_module`: default. Builds a one-node design context directly from the benchmark prompt and interface, then runs the orchestrator/worker pipeline on that direct context.
  `orchestrated`: runs the benchmark spec-normalization and planner path before orchestration.
  `legacy_lightweight`: compatibility path. You can also force this per run with `benchmark run --legacy-lightweight`.
- `benchmark.prompt_mode`
  `raw_verilog_eval`: default. Preserve the benchmark prompt verbatim for implementation/debug workers.
  `normalized`: use the normalized behavior summary instead.
- `benchmark.disable_tb_generation`
  Default `true`. Prevents benchmark runs from generating their own TB when the public/oracle TB should be used.
- `benchmark.debug_rtl_only`
  Default `true`. Keeps benchmark repair focused on DUT RTL instead of modifying the public TB harness.
- `benchmark.use_public_testbench`
  Default `true`. Repoints design context to the benchmark-supplied TB/reference assets.
- `benchmark.interface_equivalence`
  `canonical_width`: default. Canonicalizes numeric widths so equivalent ranges such as `[3:1]` and `[2:0]` match.
  `strict`: require exact width token agreement.
- `benchmark.rtl_language`
  `systemverilog`: default. Allows benchmark workers to emit/use `logic`, `always_ff`, and `always_comb`.
  `verilog2001`: keeps the older stricter prompt/sanitization behavior.

Important constraint:
- `benchmark.disable_tb_generation: true` requires `benchmark.use_public_testbench: true`.

## Benchmark CLI Interaction
- `benchmark run` reads benchmark paths/profiles from this section unless overridden by CLI flags.
- `benchmark run` also records resolved benchmark flow/prompt/execution-policy fields in `run_manifest.json`.
- `benchmark run --legacy-lightweight` overrides `benchmark.flow_mode` for that invocation only.
- `benchmark run --output-root` overrides `benchmark.output_root` for that invocation.
- Run artifacts are written to `<output_root>/<campaign>/<run_id>/...` by default.
- `benchmark analyze` consumes an existing mode directory containing official summary artifacts.

## Example Benchmark YAML
```yaml
benchmark:
  flow_mode: direct_single_module
  prompt_mode: raw_verilog_eval
  disable_tb_generation: true
  debug_rtl_only: true
  use_public_testbench: true
  interface_equivalence: canonical_width
  rtl_language: systemverilog
```

## Practical Configuration Hygiene
1. Keep team-shared behavior in YAML (`config/runtime*.yaml` variants).
2. Keep secrets (API keys, tokens) in environment variables, not YAML.
3. Use explicit presets in commands and campaign files for reproducibility.
4. Record run identity with meaningful campaign/run IDs in benchmark workflows.

## Related Code
- `config/runtime.yaml`
- `core/runtime/config.py`
