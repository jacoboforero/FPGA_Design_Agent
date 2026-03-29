# Homebrew Demo Packaging

This directory contains the demo-oriented Homebrew packaging assets for the
installed CLI path.

## Files

- `runtime.yaml`
  - Locked runtime config for the installed CLI.
  - Uses interactive spec helper + `testbench-agent` verification.
- `requirements.txt`
  - Minimal Python dependencies for the installed CLI bundle.
- `Formula/mhd.rb`
  - Reference Homebrew formula for a future real tap.
  - Treat RabbitMQ as a runtime prerequisite rather than a formula dependency.

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
- disables Homebrew auto-update and install cleanup by default to keep demo setup faster

## Runtime Prerequisites

- RabbitMQ must already be installed and running.
- `OPENAI_API_KEY` must be set for interactive spec-helper flows.
- If broker credentials differ from the locked runtime YAML, set
  `RABBITMQ_URL` explicitly in the environment.

## macOS Note

Homebrew source-formula installs require current Command Line Tools. If the
smoke script fails with an outdated-CLT error, update Command Line Tools before
retrying the real `brew install` path.
