# CLI Usage

This CLI lives under `apps/cli/cli.py` and provides commands to generate planner outputs, run the full pipeline, or exercise individual workers.

## Prerequisites
- RabbitMQ running (from `infrastructure/docker-compose.yml`): `cd infrastructure && docker-compose up -d`
- Python deps: `pip install -e .` from repo root
- Tooling (for real runs): Verilator (`verilator`), Icarus Verilog (`iverilog`, `vvp`) on PATH (or override via env: `VERILATOR_PATH`, `IVERILOG_PATH`, `VVP_PATH`)
- Optional LLM: set `USE_LLM=1` and provider keys in `.env` (`OPENAI_API_KEY` or `GROQ_API_KEY`)

## Commands

```bash
# Generate design_context.json and dag.json
python apps/cli/cli.py plan

# Run full pipeline (planner -> start workers -> orchestrator)
python apps/cli/cli.py run --timeout 120

# Run lint on an RTL file
python apps/cli/cli.py lint --rtl path/to/module.sv

# Run simulation on RTL (+ optional testbench)
python apps/cli/cli.py sim --rtl path/to/module.sv --testbench path/to/module_tb.sv
```

## Workflow (demo/full run)
1) Start RabbitMQ (`docker-compose up -d` in `infrastructure/`)
2) Ensure dependencies/tools and LLM env (optional) are set
3) `python apps/cli/cli.py run`
   - Planner stub writes `artifacts/generated/{design_context.json, dag.json}`
   - Workers (agents + deterministic) start in-process
   - Orchestrator publishes/consumes tasks through RabbitMQ until DONE/timeout
4) Inspect artifacts:
   - Generated RTL/TB: `artifacts/generated/rtl/`
   - Logs/artifact paths: `artifacts/task_memory/<node>/<stage>/`

If tools/LLM are missing, the CLI falls back to mocks and still completes. Use `--timeout` to adjust pipeline runtime.
