# Benchmark Run Workflow

Last verified against runtime behavior: March 19, 2026.

This runbook covers how to run VerilogEval-compatible benchmarks in this repo and how to interpret outputs.

This workflow is designed for researchers comparing models, settings, and system behavior in a reproducible way.

## What This Page Is For
Use this page when your goal is benchmark execution, reproducible campaign runs, and model/system comparisons with official-style scoring artifacts.

## What This Page Is Not For
- It is not the interactive hardware engineering flow. For that, use [interactive-run.md](./interactive-run.md).
- It is not a deep internals page for orchestration details. For internals, use [architecture.md](../architecture.md).

## Research Success Criteria
A successful benchmark workflow means:
1. Preflight checks pass (toolchain, broker, analyzer dependency, prompts/framework).
2. Run artifacts are created in deterministic run directories.
3. Official analyzer outputs (`summary.txt`, `summary.csv`) are present.
4. Local aggregate (`aggregate.json`) and run metadata (`run_manifest.json`) are present.
5. You can compare runs with structured delta output.

## Command Modes
`cli.py benchmark` supports explicit research workflows:
- `run`: generate benchmark samples and official scoring artifacts.
- `analyze`: parse existing `summary.txt`/`summary.csv` and emit `aggregate.json`.
- `compare`: compare two benchmark mode folders (`canonical`/`sampled`) and report metric deltas.
- `list-problems`: list discovered benchmark cases from prompts/dataset mapping.

Default behavior remains `run` if no command is provided.

## Fastest Path (15-Minute Research First Success)
From repo root:

```bash
make build
make up
make deps
make shell
```

Then inside the container shell:

```bash
export RABBITMQ_URL=amqp://user:password@rabbitmq:5672/
echo "$RABBITMQ_URL"
git submodule update --init --recursive
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark list-problems --config config/runtime.benchmark.yaml --max-problems 3
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign smoke --run-id smoke001 --max-problems 3 --dry-run
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign smoke --run-id smoke001 --max-problems 3
```

The `echo` line should print `amqp://user:password@rabbitmq:5672/`.
Use that explicit export even if `.env` points to `localhost`; inside the container, the broker host is `rabbitmq`.

Then compare against a second run (for example, another config/model setting):

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark compare \
  --left-dir artifacts/benchmarks/verilog_eval/smoke/smoke001/canonical \
  --right-dir artifacts/benchmarks/verilog_eval/smoke/smoke002/canonical \
  --compare-out artifacts/benchmarks/verilog_eval/smoke/compare_smoke001_vs_smoke002.json
```

Host fallback:

```bash
poetry install -E openai --with dev
git submodule update --init --recursive
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark
```

## End-to-End Run Flow
For each sample in `run` mode:
1. Load prompt/test/reference assets for a problem.
2. Select the benchmark flow from runtime config (`benchmark.flow_mode`) unless `--legacy-lightweight` is set.
3. In `direct_single_module` mode, build a one-node design context directly from the benchmark prompt and resolved target interface.
4. In `orchestrated` mode, run the benchmark spec-normalization and planner path to produce design context and DAG artifacts.
5. In `legacy_lightweight` mode, use the compatibility generation path without the orchestrated worker pipeline.
6. Bind benchmark oracle assets according to benchmark execution policy.
7. Run generation, lint/debug/repair, and sample compile/simulation (`iverilog` + `vvp`) against benchmark oracle assets.

After sample generation/testing completes, official analyzer (`sv-iv-analyze`) produces `summary.txt` and `summary.csv`.

## Important Runtime Behavior
- Default benchmark flow is `direct_single_module`.
- Default benchmark prompt handling is `raw_verilog_eval`, so implementation/debug workers receive the original prompt text instead of only a normalized summary.
- `--legacy-lightweight` overrides YAML flow selection for one run and forces the compatibility path.
- To reproduce the older planner-normalized benchmark path, set `benchmark.flow_mode: orchestrated` in the runtime YAML used for the run.
- Benchmark defaults disable TB generation, restrict debug to RTL edits, and bind the benchmark-provided public testbench/reference assets.
- Benchmark RTL defaults to `systemverilog`; set `benchmark.rtl_language: verilog2001` if you want the older restriction.
- Interface checks canonicalize numeric ranges by width by default, so equivalent declarations such as `[3:1]` and `[2:0]` are accepted.
- Sample generation failures are logged per sample and execution continues to remaining samples.
- Placeholder sample files may be emitted so official analysis can still run to completion.
- Final benchmark scoring still comes from official analyzer outputs.
- Queue purge behavior is optional via `--purge-queues` (important for shared environments).

## Prerequisites
You need:
- reachable RabbitMQ broker,
- LLM credentials matching configured provider,
- `verilator` for orchestrated lint stages,
- `iverilog` and `vvp` for sample simulation,
- analyzer dependency (`langchain.schema`) available in runtime environment,
- initialized VerilogEval submodule contents.

Quick preflight command:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark
```

## Main Commands
List discovered benchmark cases:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark list-problems --config config/runtime.benchmark.yaml
```

Canonical run (safe run directory layout):

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign wavefix_smoke
```

Canonical + sampled:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign wavefix_smoke --sampled
```

Legacy lightweight fallback:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign wavefix_smoke --legacy-lightweight
```

Config-controlled orchestrated fallback:

```yaml
benchmark:
  flow_mode: orchestrated
  prompt_mode: normalized
  rtl_language: verilog2001
```

Run it with:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.your_benchmark.yaml --campaign wavefix_smoke
```

Targeted runs:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign wavefix_smoke --max-problems 25
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign wavefix_smoke --only-problem Prob079
```

Dry-run plan only:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign wavefix_smoke --max-problems 10 --dry-run
```

Analyze existing run outputs:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark analyze --build-dir artifacts/benchmarks/verilog_eval/wavefix_smoke/run_001/canonical
```

Compare two runs:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark compare \
  --left-dir artifacts/benchmarks/verilog_eval/wavefix_smoke/run_001/canonical \
  --right-dir artifacts/benchmarks/verilog_eval/wavefix_smoke/run_002/canonical \
  --compare-out artifacts/benchmarks/verilog_eval/wavefix_smoke/compare_run001_vs_run002.json
```

Campaign sweeps from YAML:

```bash
PYTHONPATH=. poetry run python3 scripts/run_benchmark_campaign.py --campaign-file benchmarks/verilog_eval/campaign.example.yaml
```

Campaign authoring details:
- See [benchmark-campaigns.md](./benchmark-campaigns.md).

## Key Run Flags
- `--campaign <name>` and `--run-id <id>`: deterministic run directory naming.
- `--run-dir <path>`: explicit run directory override.
- `--sampled`: run sampled profile in addition to canonical.
- `--legacy-lightweight`: override `benchmark.flow_mode` and use the compatibility generation path.
- `--pipeline-timeout <seconds>`: per-sample orchestrated timeout.
- `--max-problems <N>` and `--only-problem`: restrict problem scope.
- `--resume`: skip samples that already have sample SV and sample test log.
- `--overwrite`: replace existing run directory.
- `--purge-queues`: optional queue purge before benchmark mode start (unsafe for shared environments).
- `--dry-run`: print execution plan without running generation.

## Expected Checkpoints
These checkpoints make long-running benchmark jobs easier to operate and debug.

### Checkpoint 1: Discovery and Plan
What you should observe:
- `list-problems` returns recognized problem IDs.
- `run --dry-run` prints run directory, campaign, run id, problem count, benchmark `flow_mode`, prompt mode, and profile choices.

### Checkpoint 2: Run Directory and Manifest
What you should observe:
- Run directory exists at `<output_root>/<campaign>/<run_id>/`.
- `run_manifest.json` is present with run metadata (`runtime.run`, provider/model, flags, filters).

Sanity checks:

```bash
ls artifacts/benchmarks/verilog_eval/<campaign>/<run_id>
cat artifacts/benchmarks/verilog_eval/<campaign>/<run_id>/run_manifest.json
```

### Checkpoint 3: Mode Outputs
What you should observe:
- `canonical/` always exists for successful run mode.
- `sampled/` exists when `--sampled` is requested.

Each mode should include:
- `summary.txt`
- `summary.csv`
- `aggregate.json`

### Checkpoint 4: Per-Problem Logs
What you should observe:
- `<ProbNNN>/` folders with sample SV outputs and sample logs.
- `pipeline_sampleXX/` snapshots for orchestrated and direct benchmark worker traces.
- `generated/benchmark_prompt.txt` for direct and raw-prompt benchmark runs.

### Checkpoint 5: Compare Report
What you should observe:
- `benchmark compare` prints or writes structured JSON with left/right metrics and delta values.

## Output Layout
Default root:
- `artifacts/benchmarks/verilog_eval/`

Per run:
- `<campaign>/<run_id>/run_manifest.json`
- `<campaign>/<run_id>/canonical/`
- `<campaign>/<run_id>/sampled/` (if enabled)

Per mode (`canonical/`, `sampled/`):
- `summary.txt` (official analyzer output)
- `summary.csv` (official analyzer output)
- `aggregate.json` (local structured summary)
- `<ProbNNN>/` per-problem directory with:
  - generated sample SV files,
  - sample generate logs,
  - sample compile/run logs,
  - `pipeline_sampleXX/` trace snapshots.

## Troubleshooting by Symptom

### Symptom: `doctor` fails framework/prompt checks
Symptoms:
- Missing framework scripts/datasets.
- Missing prompts directory.

Actions:
1. Run `git submodule update --init --recursive`.
2. Validate `benchmark.verilog_eval_root` and `benchmark.prompts_dir` in config.
3. Re-run doctor.

### Symptom: broker/tool dependency failures before run starts
Symptoms:
- Broker unreachable, or missing `verilator`/`iverilog`/`vvp`.

Actions:
1. Run `PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark`.
2. Fix broker reachability and tool path resolution (`tools.*` in runtime config).
3. Retry with `run --dry-run` first to confirm setup.

### Symptom: `ModuleNotFoundError: pika` or other Python package import errors
Symptoms:
- CLI exits immediately before doctor or benchmark logic starts.

Actions:
1. In Docker, run `make deps` before opening `make shell`.
2. Invoke the CLI with `PYTHONPATH=. poetry run python3 ...` instead of bare `python3`.
3. On the host, run `poetry install -E openai --with dev` before using the CLI.

### Symptom: run fails because output directory already exists
Symptoms:
- Error indicating run/mode directory exists.

Actions:
1. Use `--resume` when continuing an interrupted run.
2. Use `--overwrite` when intentionally replacing a run.
3. Avoid accidental clobber by setting explicit `--run-id` values.

### Symptom: compare mode says path is ambiguous
Symptoms:
- Error indicates both canonical and sampled are present.

Actions:
1. Pass explicit mode directories (`.../canonical` or `.../sampled`) to `--left-dir` and `--right-dir`.

### Symptom: repeated generation failures for specific problems
Symptoms:
- Warnings for sample generation failures continue but run completes.

Actions:
1. Inspect problem sample logs (`*-sv-generate.log`, `*-sv-iv-test.log`).
2. Inspect `pipeline_sampleXX/` snapshots for orchestrated details.
3. Use `--only-problem` to isolate and rerun with more focused debugging.

### Symptom: analyzer dependency error (`langchain.schema`)
Symptoms:
- Run/analyze phase fails with missing analyzer dependency.

Actions:
1. Install required dependency in runtime env (`langchain<0.2` as documented).
2. Re-run doctor benchmark checks.

## Researcher Next Steps
1. Use [benchmark-campaigns.md](./benchmark-campaigns.md) to run structured sweeps across model/config variants.
2. Use [benchmark-methodology.md](../benchmark-methodology.md) to interpret deltas and avoid weak comparisons.
3. Use [artifact-hygiene.md](./artifact-hygiene.md) and [observability.md](../observability.md) to keep campaign outputs searchable and auditable.

## Related Code
- `apps/cli/run_verilog_eval.py`
- `scripts/run_benchmark_campaign.py`
- `benchmarks/verilog_eval/campaign.example.yaml`
- `tests/apps/test_run_verilog_eval.py`
- `tests/apps/test_run_benchmark_campaign.py`
- `apps/cli/doctor.py`
- `config/runtime.yaml`
