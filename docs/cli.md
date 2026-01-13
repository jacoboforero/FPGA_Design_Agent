# CLI usage

Entrypoint: `apps/cli/cli.py`. Run with `PYTHONPATH=.` from repo root.

## Prereqs
- RabbitMQ running: `cd infrastructure && docker-compose up -d`
- Python deps: `poetry install`
- Optional tools: `verilator`, `iverilog`, `vvp` on PATH (or set `VERILATOR_PATH`, `IVERILOG_PATH`, `VVP_PATH`)
- LLM required: set `USE_LLM=1` and provider keys (`OPENAI_API_KEY`/`GROQ_API_KEY`)

## Command
```bash
# Interactive spec -> plan -> run in one command
python apps/cli/cli.py --timeout 120 [--run-name my_run]
```
The CLI prompts you to press Enter to open `$EDITOR` so you can paste the initial specification.

## Typical flows
- **With LLM + tools:**
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
