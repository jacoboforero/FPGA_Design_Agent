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
- When Python dependencies change, regenerate the lockfile from the Docker toolchain with `make lock`, then verify it with `make lock-check`.
- Prefer `poetry add ...` / `poetry remove ...` inside the `app` container over manual edits to `pyproject.toml`.

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

Installed `mhd` now behaves like a standard macOS CLI:
- it reads credentials from the shell environment,
- it seeds user config into `$XDG_CONFIG_HOME/mhd` or `~/.config/mhd`,
- it does not auto-load `.env` from the current working directory,
- it enables OpenAI-backed RAG for normal engineer/demo runs and surfaces that through narration,
- it lets you override RAG per run with `--rag on` or `--rag off`,
- it uses a staged runtime payload instead of copying the whole repo into Homebrew `libexec`.

The repo smoke helper builds a temporary local tap from the current working
tree and exercises the installed command:

```bash
bash scripts/test_homebrew_install.sh
```

If you want the full installed CLI smoke too:

```bash
MHD_RUN_FULL_SMOKE=1 bash scripts/test_homebrew_install.sh
```

By default, that full smoke uses `tests/test_specs/01_counter3_basic.txt`, the
current safest live engineer demo fixture. You can override it with
`MHD_SMOKE_SPEC=/absolute/path/to/spec.txt`.
The helper also pins the full smoke broker to `amqp://guest:guest@localhost:5672/`
unless you override it with
`MHD_SMOKE_RABBITMQ_URL=amqp://user:password@host:5672/`.

Runtime notes:
- `mhd doctor` verifies the installed config, credentials, and tools.
- `mhd doctor` also verifies OpenAI-backed RAG readiness when `rag.enabled=true`.
- first installed run seeds `runtime.yaml`, `runtime.benchmark.yaml`, and `tool_registry.yaml` into the user config home.
- RabbitMQ must already be installed and running.
- add `OPENAI_API_KEY` and optional `RABBITMQ_URL` to `~/.zshrc`, then open a new shell.
- `MHD_ENV_FILE=/absolute/path/to/.env` remains available as an explicit advanced override.
- Source-based Homebrew installs require current macOS Command Line Tools.
- Use `bash scripts/setup_homebrew_demo_env.sh` to prepare a clean demo workspace with sample specs only.

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
- `--config`: choose runtime manifest explicitly. Repo engineer default is `config/runtime.yaml`; installed engineer default is `~/.config/mhd/runtime.yaml` unless `XDG_CONFIG_HOME` is set.
- `--timeout`: pipeline timeout in seconds (`0` disables timeout).
- `--spec-file`: run non-interactively from a spec file.
- `--run-name`: label observability artifacts.
- `--narrative-mode {llm,deterministic,off}`: control execution narration.
- `--rag {on,off}`: override `rag.enabled` for just this run.

Benchmark flow flags:
- `--config`: choose runtime manifest explicitly. Benchmark subcommands default to `config/runtime.benchmark.yaml` in dev and `~/.config/mhd/runtime.benchmark.yaml` when installed.
- `--campaign`, `--run-id`, `--run-dir`: control run identity and run directory layout.
- `--sampled`, `--legacy-lightweight`, `--pipeline-timeout`: benchmark execution behavior.
- `--resume`, `--overwrite`, `--dry-run`: run safety and controllability.
- `--max-problems`, `--only-problem`: discovery filtering controls.
- `--purge-queues`: optional benchmark queue purge.

## Runtime Ownership Notes
- Runtime behavior comes from YAML manifests.
- Dev engineer runs default to `config/runtime.yaml`.
- Dev benchmark runs default to `config/runtime.benchmark.yaml`.
- Installed engineer runs default to `$XDG_CONFIG_HOME/mhd/runtime.yaml` or `~/.config/mhd/runtime.yaml`.
- Installed benchmark runs default to `$XDG_CONFIG_HOME/mhd/runtime.benchmark.yaml` or `~/.config/mhd/runtime.benchmark.yaml`.
- Installed tool-command overrides live at `$XDG_CONFIG_HOME/mhd/tool_registry.yaml` or `~/.config/mhd/tool_registry.yaml`.
- `run.spec_profile` and `run.verification_profile` are selected inside the YAML, not by CLI preset flags.
- API keys and secrets remain environment-driven.
- `rag.allow_benchmark=false` keeps benchmark runs reproducible by default.
- demo guidance: use `--rag off` for the counter walkthrough and `--rag on` for the curated multimodule walkthrough.
- Prefer explicit config files and run labels for reproducibility.

## Related Code
- `apps/cli/cli.py`
- `apps/cli/spec_flow.py`
- `apps/cli/doctor.py`
- `apps/cli/run_verilog_eval.py`
- `scripts/run_benchmark_campaign.py`
