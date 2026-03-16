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
make build
make up
make deps
make shell
```

Then inside the container shell:

```bash
export RABBITMQ_URL=amqp://user:password@rabbitmq:5672/
git submodule update --init --recursive
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --preset benchmark --benchmark
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --preset benchmark --campaign smoke
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --preset benchmark --campaign smoke --sampled
```

List available benchmark cases:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark list-problems --preset benchmark
```

Compare two benchmark mode directories:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark compare --left-dir <run_a>/canonical --right-dir <run_b>/canonical
```

Run multi-entry campaigns from YAML:

```bash
PYTHONPATH=. poetry run python3 scripts/run_benchmark_campaign.py --campaign-file benchmarks/verilog_eval/campaign.example.yaml
```

## Optional Prompt Overrides
- Place custom prompt files under `benchmarks/verilog_eval/prompt_overrides/`
- Point `benchmark.prompts_dir` to that folder only for custom experiments
- Keep official benchmarking pointed at the upstream dataset for comparability

## Optional Oracle Manifest
- Use `benchmark.oracle_manifest` in runtime config to pin custom `test_sv`/`ref_sv` paths
- Template: `benchmarks/verilog_eval/oracle_manifest.example.json`
