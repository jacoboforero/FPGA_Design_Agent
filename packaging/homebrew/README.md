# Homebrew Demo Packaging

This directory contains the demo-oriented Homebrew packaging assets for the
installed CLI path.

## Files

- `requirements.txt`
  - Runtime Python dependencies for the installed CLI bundle.
- `stage_runtime.py`
  - Builds the curated install payload used by the Homebrew formula.
  - Stages only runtime code, `config/`, `tool_registry.yaml`, the shipped RAG knowledge base, and benchmark assets required by `mhd benchmark`.
- `Formula/mhd.rb`
  - Reference Homebrew formula for a future real tap.
  - Seeds user config into `$XDG_CONFIG_HOME/mhd` or `~/.config/mhd` on first run.
  - Treats RabbitMQ as a runtime prerequisite rather than a formula dependency.

## Local Tap Smoke Test

Use the repo helper to test a real Homebrew-style install from the current
working tree:

```bash
bash scripts/test_homebrew_install.sh
```

The script:

1. packages the current working tree into a tarball,
2. creates a temporary local tap,
3. installs `mhd` via `brew install <tap>/mhd`,
4. runs `mhd --help` and `mhd doctor`,
5. optionally runs a full CLI smoke with `MHD_RUN_FULL_SMOKE=1`.

Full-smoke notes:

- defaults to the safer current engineer demo spec: `tests/test_specs/01_counter3_basic.txt`
- override the spec with `MHD_SMOKE_SPEC=/absolute/path/to/spec.txt`
- defaults the full smoke broker to `amqp://guest:guest@localhost:5672/`
- override the broker with `MHD_SMOKE_RABBITMQ_URL=amqp://user:password@host:5672/`
- uses a temporary `XDG_CONFIG_HOME` so the smoke test does not pollute your real user config
- disables Homebrew auto-update and install cleanup by default to keep demo setup faster

## Runtime Prerequisites

- RabbitMQ must already be installed and running.
- `mhd` reads credentials from the shell environment.
- Add `OPENAI_API_KEY` and optional `RABBITMQ_URL` to `~/.zshrc`, then open a new shell.
- `OPENAI_API_KEY` powers both the default LLM path and OpenAI-backed RAG embeddings in the demo flow.
- Use `--rag off` and `--rag on` on the installed command to control retrieval per run without editing YAML.
- `MHD_ENV_FILE=/absolute/path/to/.env` remains available as an explicit advanced override.

## Installed User Config

- Installed `mhd` mirrors the repo config tree under `$XDG_CONFIG_HOME/mhd` when `XDG_CONFIG_HOME` is set.
- Otherwise it uses `~/.config/mhd`.
- First run seeds that directory from the bundled `config/` templates.
- Existing user config is never overwritten automatically.
- The old `/opt/homebrew/etc/mhd/runtime.yaml` path is no longer part of the install contract.
- Normal installed defaults are:
  - `mhd ...` -> `runtime.yaml`
  - `mhd benchmark ...` -> `runtime.benchmark.yaml`
  - `mhd doctor --benchmark` -> `runtime.benchmark.yaml`

## Install Payload

The Homebrew install intentionally stages a smaller runtime tree. It includes:

- `adapters/`, `agents/`, `apps/cli/`, `core/`, `orchestrator/`, `workers/`
- `config/`
- `tool_registry.yaml`
- the shipped Verilog RAG knowledge base under `adapters/rag/`
- the benchmark assets needed by `mhd benchmark`

It excludes repo-only material such as:

- `docs/`
- `tests/`
- `infrastructure/`
- `apps/ui_backend/`
- `apps/vscode-extension/`
- repo `.env` files and cache artifacts

## Demo Workspace Helper

To create a clean demo workspace that looks like a real user directory:

```bash
bash scripts/setup_homebrew_demo_env.sh
```

That helper:

- creates `~/Desktop/mhd-homebrew-demo` by default,
- copies only the demo spec files needed for the live walkthrough,
- seeds `artifacts/rag/memory.json` with a single curated `buf1_leaf` example for the multimodule demo,
- prints shell export lines for `~/.zshrc`,
- does not copy config into the workspace,
- does not create a workspace `.env`,
- relies on the installed config + shell environment the same way a real user would.

## macOS Note

Homebrew source-formula installs require current Command Line Tools. If the
smoke script fails with an outdated-CLT error, update Command Line Tools before
retrying the real `brew install` path.
