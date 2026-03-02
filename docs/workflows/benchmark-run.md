# Benchmark Run Workflow

## Purpose
Provide a complete runbook to configure, execute, and interpret VerilogEval-compatible benchmarks in this repository.

## Audience
Engineers running benchmarks, tuning benchmark settings, or reviewing benchmark outputs.

## Scope
Prerequisites, runtime configuration, command semantics, artifact layout, and troubleshooting for `apps/cli/cli.py benchmark`.

## End-to-End Flow
The benchmark runner executes this sequence:
1. Load prompt cases from `benchmark.prompts_dir` (default `third_party/verilog-eval/dataset_spec-to-rtl`, IDs like `Prob079`).
2. For each sample, run local benchmark planning (`spec_flow` + `planner.generate_from_specs`) as a decoupled planning phase.
3. Execute the full orchestrated pipeline (queues/workers/orchestrator, including repair loop) to produce RTL.
4. Compile and simulate each generated sample with `iverilog` + `vvp` against official test/reference SV files.
5. Run official VerilogEval analyzer (`third_party/verilog-eval/scripts/sv-iv-analyze`) to produce `summary.txt` and `summary.csv`.
6. Write local `aggregate.json` as a machine-friendly rollup of official artifacts.

## Required Prerequisites
All commands below assume repo root as the current working directory.

### 1) Framework assets
```bash
git submodule update --init --recursive
```
Expected files:
- `third_party/verilog-eval/scripts/sv-iv-analyze`
- `third_party/verilog-eval/Makefile.in`
- `third_party/verilog-eval/dataset_spec-to-rtl/`

### 2) LLM credentials
Benchmark generation uses orchestrated agent workers (implementation/testbench/debug/reflection as needed):
- if `llm.provider: openai`, set `OPENAI_API_KEY`
- if `llm.provider: groq`, set `GROQ_API_KEY`

### 3) Broker
RabbitMQ must be reachable for orchestrated benchmark execution (same requirement as full pipeline runs).

### 4) Toolchain
`verilator` must be available for orchestrated lint/tb_lint stages.

### 5) Simulation tools
`iverilog` and `vvp` must be available either on PATH or explicitly configured:
- `tools.iverilog_path`
- `tools.vvp_path`

### 6) Analyzer dependency
Official analyzer currently imports `langchain.schema`:
```bash
poetry run pip install 'langchain<0.2'
```

### 7) Preflight (recommended)
```bash
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset benchmark --benchmark
```
This checks runtime preset load, provider credentials, framework files, prompt discovery, broker reachability, verilator, sim tools, and analyzer dependency.

## Runtime Configuration Explained
Primary config file: `config/runtime.yaml`.

### Minimal benchmark-ready config shape
```yaml
presets:
  benchmark:
    spec_profile: benchmark
    verification_profile: oracle_compare
    allow_repair_loop: true
    interactive_spec_helper: false
    benchmark_mode: true

llm:
  enabled: true
  provider: openai
  default_model: gpt-4.1-mini

tools:
  verilator_path: null
  iverilog_path: null
  vvp_path: null

benchmark:
  verilog_eval_root: third_party/verilog-eval
  prompts_dir: third_party/verilog-eval/dataset_spec-to-rtl
  output_root: artifacts/benchmarks/verilog_eval
  oracle_manifest: null
  canonical: { n: 1, temperature: 0.0, top_p: 0.01 }
  sampled: { n: 20, temperature: 0.8, top_p: 0.95 }
```

### Which config fields matter most
- `benchmark.verilog_eval_root`: framework root used for dataset and analyzer scripts.
- `benchmark.prompts_dir`: source prompt directory scanned for benchmark cases.
- `benchmark.output_root`: where `canonical/` and `sampled/` run directories are created.
- `benchmark.oracle_manifest`: optional JSON mapping problem IDs to explicit test/ref paths.
- `benchmark.canonical.*`: sample count and decode settings used in the canonical run.
- `benchmark.sampled.*`: sample count and decode settings used when `--sampled` is passed.
- `tools.verilator_path`: explicit path for orchestrated benchmark lint stages.
- `tools.iverilog_path` and `tools.vvp_path`: explicit tool paths if PATH lookup is not enough.
- `llm.provider` and provider credentials: required for sample generation.
- `llm.default_model`: model used by benchmark agent workers.

### Important behavior about presets
The benchmark command loads your selected preset (`--preset`, default `benchmark`) but benchmark generation itself enforces benchmark policy internally (non-interactive benchmark flow and benchmark execution policy). Keep the benchmark preset aligned with benchmark defaults to avoid confusion and to keep doctor output accurate.

### `oracle_manifest` format (optional)
When present, this overrides dataset auto-resolution for listed problems.

Example (`config/oracle_manifest.json`):
```json
{
  "Prob004": {
    "test_sv": "Prob004_vector2_test.sv",
    "ref_sv": "Prob004_vector2_ref.sv"
  },
  "Prob079": {
    "test_sv": "/abs/path/to/Prob079_test.sv",
    "ref_sv": "/abs/path/to/Prob079_ref.sv"
  }
}
```
Notes:
- relative paths are resolved under `benchmark.verilog_eval_root/dataset_spec-to-rtl`
- absolute paths are used as-is
- missing referenced files cause a hard failure

## Commands and What Each One Does
### Preflight check before running
```bash
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset benchmark --benchmark
```
Purpose: validate local environment and config before spending generation time.

### Canonical run (default benchmark mode)
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark
```
Purpose: runs orchestrated benchmark canonical mode only (`benchmark.canonical`).

### Canonical + sampled run
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --sampled
```
Purpose: runs canonical first, then sampled profile (`benchmark.sampled`) into a separate output tree.

### Legacy lightweight fallback (explicit only)
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --legacy-lightweight
```
Purpose: use previous one-shot implementation generation path for compatibility/debugging.

### Limit run scope
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --max-problems 25
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --only-problem Prob079
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --only-problem Prob004 --only-problem Prob079
```
Purpose: reduce runtime for smoke checks or targeted debugging.

### Analyze-only mode
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --build-dir artifacts/benchmarks/verilog_eval/canonical
```
Purpose: skip generation and simulation; only parse existing `summary.txt` and `summary.csv` into `aggregate.json`.

## CLI Options Reference
- `--config <path>`: runtime YAML path; default `config/runtime.yaml`.
- `--preset <name>`: preset to load; default `benchmark`.
- `--sampled`: additionally run sampled mode.
- `--legacy-lightweight`: use previous direct implementation-only benchmark generation path.
- `--pipeline-timeout <seconds>`: per-sample orchestrated pipeline timeout; default `180`.
- `--max-problems <N>`: cap number of discovered prompt cases; `0` means all.
- `--only-problem ProbNNN`: include only selected problem IDs; repeatable.
- `--build-dir <dir>`: analyze-only mode on an existing benchmark build directory.

## Prompt and Dataset Resolution Rules
- Prompt discovery prefers official `*_prompt.txt` files under `benchmark.prompts_dir`.
- Legacy compatibility is preserved: if official prompt files are absent for a problem, `ProbNNN*.txt` files are accepted.
- Non-problem text files (for example `problems.txt`) are ignored.
- For each problem, test/reference SV is resolved from dataset patterns unless overridden by `oracle_manifest`.
- If `--only-problem` includes IDs not found in discovered cases, the run fails fast.

## Output Layout and Interpretation
Default base output directory:
- `artifacts/benchmarks/verilog_eval/`

Canonical run outputs:
- `artifacts/benchmarks/verilog_eval/canonical/summary.txt`
- `artifacts/benchmarks/verilog_eval/canonical/summary.csv`
- `artifacts/benchmarks/verilog_eval/canonical/aggregate.json`
- `artifacts/benchmarks/verilog_eval/canonical/<ProbNNN>/` per-problem sample directories
- `artifacts/benchmarks/verilog_eval/canonical/<ProbNNN>/*_sampleXX.sv` generated RTL samples
- `artifacts/benchmarks/verilog_eval/canonical/<ProbNNN>/*-sv-generate.log` generation logs
- `artifacts/benchmarks/verilog_eval/canonical/<ProbNNN>/*-sv-iv-test.log` compile/simulation logs
- `artifacts/benchmarks/verilog_eval/canonical/<ProbNNN>/pipeline_sampleXX/` full per-sample pipeline traces

Sampled run outputs:
- same structure under `artifacts/benchmarks/verilog_eval/sampled/`

How to read results:
- `summary.txt` and `summary.csv` are official analyzer outputs.
- `aggregate.json` is an internal structured summary derived from official artifacts.

## Performance and Cost Expectations
- Total sample executions = `number_of_cases * n` where `n` is from selected sample config.
- Each sample executes the full orchestrated pipeline (and can trigger repair-loop retries), so cost/runtime are materially higher than the legacy lightweight path.
- Canonical (`n=1`) is best for quick correctness checks.
- Sampled (`n=20` by default) is much slower and more expensive because it multiplies LLM calls and compile/sim runs.

## Common Failures and Fixes
- Framework not initialized: run `git submodule update --init --recursive`.
- Missing `langchain.schema`: run `poetry run pip install 'langchain<0.2'`.
- RabbitMQ unreachable: verify broker is up and runtime broker settings are correct.
- `verilator` unavailable: install tool or set `tools.verilator_path`.
- `iverilog` or `vvp` unavailable: install tools or set `tools.iverilog_path` and `tools.vvp_path`.
- LLM gateway unavailable: set provider key and keep `llm.enabled: true`.
- Prompt directory missing or empty: verify `benchmark.prompts_dir` points to an official VerilogEval dataset directory or an explicit override directory.
- Pipeline failure stops run immediately (fail-fast): inspect the failing sample’s `pipeline_sampleXX/` trace and `*-sv-generate.log`.
- Analyze-only directory invalid: ensure `--build-dir` contains both `summary.txt` and `summary.csv`.

## New Contributor Checklist
1. Initialize submodules.
2. Set LLM provider key matching `llm.provider`.
3. Run doctor benchmark preflight.
4. Run canonical benchmark.
5. Inspect `canonical/summary.txt`, `canonical/summary.csv`, and `canonical/aggregate.json`.
6. Run sampled only after canonical is healthy.

## Source of Truth
- `apps/cli/run_verilog_eval.py`
- `apps/cli/doctor.py`
- `apps/cli/cli.py`
- `core/runtime/config.py`
- `config/runtime.yaml`

## Related Docs
- [../benchmark-methodology.md](../benchmark-methodology.md)
- [../cli.md](../cli.md)
- [../reference/runtime-config.md](../reference/runtime-config.md)
