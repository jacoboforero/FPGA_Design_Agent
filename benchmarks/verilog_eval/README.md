# VerilogEval Integration Assets

This directory contains repository-owned benchmark integration assets. Upstream VerilogEval framework files remain under `third_party/verilog-eval`.

## Ownership Boundary
- Upstream owned: `third_party/verilog-eval/` (scripts, datasets, analyzer behavior)
- Repo owned: this directory, runtime config wiring, and `apps/cli/run_verilog_eval.py`

## Default Prompt Source
- Default benchmark prompt source is `third_party/verilog-eval/dataset_spec-to-rtl`
- Prompt discovery prefers official `*_prompt.txt` and falls back to legacy `Prob*.txt`

## Running Benchmarks
```bash
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset benchmark --benchmark
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --sampled
```

## Optional Prompt Overrides
- Place custom prompt files under `benchmarks/verilog_eval/prompt_overrides/`
- Point `benchmark.prompts_dir` to that folder only for custom experiments
- Keep official benchmarking pointed at the upstream dataset for comparability

## Optional Oracle Manifest
- Use `benchmark.oracle_manifest` in runtime config to pin custom `test_sv`/`ref_sv` paths
- Template: `benchmarks/verilog_eval/oracle_manifest.example.json`
