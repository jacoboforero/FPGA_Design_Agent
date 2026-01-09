# CLI usage

Entrypoint: `apps/cli/cli.py`. Run with `PYTHONPATH=.` from repo root.

## Prereqs
- RabbitMQ running: `cd infrastructure && docker-compose up -d`
- Python deps: `pip install -e .`
- Optional tools: `verilator`, `iverilog`, `vvp` on PATH (or set `VERILATOR_PATH`, `IVERILOG_PATH`, `VVP_PATH`)
- Optional LLM: set `USE_LLM=1` and provider keys (`OPENAI_API_KEY`/`GROQ_API_KEY`)

## Commands
```bash
# Collect and lock specs (L1–L5)
python apps/cli/cli.py spec

# Generate design_context.json + dag.json (uses locked specs; fallback stub via flags)
python apps/cli/cli.py plan [--stub | --allow-stub]

# Full pipeline (planner -> workers -> orchestrator)
python apps/cli/cli.py run --timeout 120 [--allow-stub] [--run-name my_run]

# Interactive spec -> plan -> run in one command
python apps/cli/cli.py full --timeout 120 [--run-name my_run]

# Lint once
python apps/cli/cli.py lint --rtl path/to/module.sv

# Simulate once (TB optional)
python apps/cli/cli.py sim --rtl path/to/module.sv --testbench path/to/module_tb.sv
```

## Typical flows
- **Stubbed demo (no tools/LLM):**
  ```bash
  PYTHONPATH=. USE_LLM=0 python apps/cli/cli.py run --allow-stub --timeout 60
  ```
- **With LLM + tools:**
  ```bash
  export USE_LLM=1 OPENAI_API_KEY=...
  PYTHONPATH=. python apps/cli/cli.py run --allow-stub --timeout 120 --run-name my_llm_run
  ```
- **Suite smoke (increasing complexity, non-interactive specs):**
  ```bash
  PYTHONPATH=. python apps/cli/run_suite.py --timeout 90
  # Each case auto-sets run names suite_<case> for observability/cost logs.
  ```

Artifacts end up in `artifacts/generated/` (design context + RTL/TB) and `artifacts/task_memory/<node>/<stage>/` (logs, artifact paths). Increase `--timeout` for slower sims or LLM calls.

Observability/cost tracking with AgentOps is documented in `docs/observability.md`.
