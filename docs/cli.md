# CLI usage

Entrypoint: `apps/cli/cli.py`. The recommended workflow runs it inside the pinned toolchain container.

## Prereqs
- Docker + Docker Compose
- LLM required: set `USE_LLM=1` and provider keys (`OPENAI_API_KEY`/`GROQ_API_KEY`) in `.env`

## Recommended workflow (containerized)
```bash
make build
make up
make deps
make cli
```
The CLI prompts you to press Enter to open `$EDITOR` so you can paste the initial specification.
The container includes Verilator 5.044 and Icarus (`iverilog`/`vvp`) for lint and simulation.
`make cli` and `make shell` will source `.env` if it exists, and the CLI also loads `.env` at startup.
`make deps` installs the OpenAI client extra required for LLM-backed agents.
The container sets `EDITOR=nano`; override by setting `EDITOR` in `.env` if you prefer another editor.
Inside Docker, `RABBITMQ_URL` must use the service host (`amqp://user:password@rabbitmq:5672/`). `make cli` will auto-fix localhost URLs.

Common helpers:
```bash
make shell
make test
make logs
make down
```

## Devcontainer
Open the repo in a Dev Container to use the same pinned toolchain automatically. The config uses the `app` service in `infrastructure/docker-compose.yml`.

## Host-only workflow (not recommended)
```bash
# Interactive spec -> plan -> run in one command
PYTHONPATH=. python apps/cli/cli.py --timeout 120 [--run-name my_run]
```

## Typical flows
- **With LLM + tools (host-only fallback):**
  ```bash
  export USE_LLM=1 OPENAI_API_KEY=...
  PYTHONPATH=. python apps/cli/cli.py --timeout 120 --run-name my_llm_run
  ```
- **Suite smoke (increasing complexity, non-interactive specs):**
  ```bash
  PYTHONPATH=. python apps/cli/run_suite.py --timeout 90
  # Each case auto-sets run names suite_<case> for observability/cost logs.
  ```

Artifacts end up in `artifacts/generated/` (design context + RTL/TB) and `artifacts/task_memory/<node>/<stage>/` (logs, artifact paths). Increase `--timeout` for slower sims or LLM calls.

Observability/cost tracking with AgentOps is documented in `docs/observability.md`.
