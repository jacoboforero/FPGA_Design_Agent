# CLI

Last verified against runtime behavior: March 19, 2026.

`apps/cli/cli.py` is the main entrypoint for full runs, doctor checks, and benchmark runs.

This command surface has two user modes:
- hardware-engineering mode (`cli.py` full flow) for design work,
- research mode (`cli.py benchmark`) for scripted evaluation.

## Command Environment
Run CLI commands in one of these contexts:
- inside the `app` container after `make build`, `make up`, `make deps`, `make shell`
- on the host after `poetry install --with dev`

Notes:
- `make shell` rewrites `RABBITMQ_URL=...localhost...` to the container-safe broker URL `amqp://user:password@rabbitmq:5672/`.
- If you already had a container shell open before running `make shell`, exit and reopen it so the broker URL is refreshed.
- For benchmark and other broker-backed commands inside the container, it is always safe to run `export RABBITMQ_URL=amqp://user:password@rabbitmq:5672/` before invoking the CLI.
- Prefer `PYTHONPATH=. poetry run python3 ...` for all repo CLI commands.

## What This Page Is For
Use this page to choose the right CLI entrypoint quickly and avoid running the wrong workflow.

## What This Page Is Not For
- It is not the complete engineer runbook; use [workflows/interactive-run.md](./workflows/interactive-run.md).
- It is not the complete benchmark runbook; use [workflows/benchmark-run.md](./workflows/benchmark-run.md).

## Command Decision Matrix
Use this table first when deciding what to run.

| Goal | Primary Command | Notes |
| --- | --- | --- |
| Run full engineer flow interactively | `PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml` | Includes spec collection, planning gate, orchestrated execution. |
| Validate environment before engineer run | `PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.yaml` | Verifies credentials, tools, and broker readiness for engineer runs. |
| Run benchmark generation/scoring | `PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign <name>` | Produces run-manifest + canonical mode outputs. |
| List benchmark cases before running | `PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark list-problems --config config/runtime.benchmark.yaml` | Validates prompt/discovery coverage quickly. |
| Plan benchmark run without execution | `PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign <name> --dry-run` | Non-destructive plan preview. |
| Rebuild local benchmark aggregate from existing official outputs | `PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark analyze --build-dir <mode_dir>` | Requires existing `summary.txt` and `summary.csv`. |
| Compare two benchmark mode outputs | `PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark compare --left-dir <mode_a> --right-dir <mode_b>` | Structured delta report for pass-rate and metrics. |
| Execute many benchmark runs from YAML | `PYTHONPATH=. poetry run python3 scripts/run_benchmark_campaign.py --campaign-file <path>` | Research campaign automation utility. |

## Common Commands
From repo root:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.yaml
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign smoke
```

## Homebrew Demo Install
For the demo-oriented installed CLI path, the command is `mhd`, not
`python3 apps/cli/cli.py`.

The locked installed runtime lives in `packaging/homebrew/runtime.yaml` and is
configured for:
- `run.spec_profile.interaction=interactive`
- `run.spec_profile.rigor_level=L2`
- `run.verification_profile=testbench-agent`

The repo smoke helper builds a temporary local tap from the current working
tree and exercises the installed command:

```bash
bash scripts/test_homebrew_install.sh
```

If you want the full installed CLI smoke too:

```bash
MHD_RUN_FULL_SMOKE=1 bash scripts/test_homebrew_install.sh
```

Runtime notes:
- `mhd doctor` verifies the installed config, credentials, and tools.
- RabbitMQ must already be installed and running.
- `OPENAI_API_KEY` must be set for interactive spec-helper flows.
- `RABBITMQ_URL` can override the locked broker URL if local credentials differ.
- Source-based Homebrew installs require current macOS Command Line Tools.

## Full Interactive Flow (Engineer Path)
1. Collect specs (interactive by default unless `--spec-file` is provided).
2. Run planner.
3. Display generated DAG summary.
4. Ask `Proceed to execution?` unless `--yes` is passed.
5. Execute orchestrated pipeline and print generated RTL paths/content.

## Benchmark Subcommands (Research Path)
`benchmark` mode subcommands:
- `run`
- `analyze`
- `compare`
- `list-problems`

Behavior note:
- `cli.py benchmark` without subcommand defaults to `run`.

## Useful Flags
Engineer flow flags:
- `--config`: choose runtime manifest (`config/runtime.yaml` for engineer runs).
- `--timeout`: pipeline timeout in seconds (`0` disables timeout).
- `--spec-file`: run non-interactively from a spec file.
- `--run-name`: label observability artifacts.
- `--narrative-mode {llm,deterministic,off}`: control execution narration.

Benchmark flow flags:
- `--config`: choose runtime manifest (`config/runtime.benchmark.yaml` for benchmark runs).
- `--campaign`, `--run-id`, `--run-dir`: control run identity and run directory layout.
- `--sampled`, `--legacy-lightweight`, `--pipeline-timeout`: benchmark execution behavior.
- `--resume`, `--overwrite`, `--dry-run`: run safety and controllability.
- `--max-problems`, `--only-problem`: discovery filtering controls.
- `--purge-queues`: optional benchmark queue purge.

## Runtime Ownership Notes
- Runtime behavior comes from YAML manifests.
- Normal engineer runs use `config/runtime.yaml`.
- Normal benchmark runs use `config/runtime.benchmark.yaml`.
- `run.spec_profile` and `run.verification_profile` are selected inside the YAML, not by CLI preset flags.
- API keys and secrets remain environment-driven.
- Prefer explicit config files and run labels for reproducibility.

## Related Code
- `apps/cli/cli.py`
- `apps/cli/spec_flow.py`
- `apps/cli/doctor.py`
- `apps/cli/run_verilog_eval.py`
- `scripts/run_benchmark_campaign.py`
