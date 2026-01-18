# Observability & Cost Tracking (AgentOps)

This repo now emits lightweight observability and cost data via AgentOps plus local JSON logs so you can compare runs across models/providers.

## How it works
- `core/observability/agentops_tracker.py` starts an AgentOps trace per run (if configured) and records every LLM call (model, provider, tokens, estimated cost) into `artifacts/observability/costs.jsonl`, with a rolling summary in `cost_summary.json`.
- LLM calls from spec-helper, implementation, and testbench agents are logged. Deterministic paths stay untouched.
- The global EventEmitter includes an AgentOps sink; stage transitions are tagged into the trace metadata (best-effort).
- AgentOps auto-instruments OpenAI/Groq calls when enabled; all logging is best-effort and will no-op if AgentOps is not configured.

## Configure
Install dependency (if not already installed):
```
poetry install -E observability
```

Set environment (e.g., in `.env`):
```
AGENTOPS_API_KEY=...            # required to send to AgentOps
AGENTOPS_ENABLE=1               # allow init even if API key is set elsewhere
AGENTOPS_RUN_NAME=my-run        # optional trace/run name
LLM_PROVIDER=openai|groq        # optional tag helper
OPENAI_MODEL=... / GROQ_MODEL=...  # optional tag helper
```

## CLI knobs
- `apps/cli/cli.py run|full` now accept `--run-name` (else auto-generates).
- `apps/cli/run_suite.py` creates a fresh trace per suite case (run names `suite_<case>`).

## Outputs (local)
- `artifacts/observability/costs.jsonl`: one line per LLM call, fields: `run_id`, `run_name`, `agent`, `node_id`, `model`, `provider`, token counts, estimated cost, metadata.
- `artifacts/observability/cost_summary.json`: rolling totals per run.

## Swap/compare models
1) Set `LLM_PROVIDER`/`OPENAI_MODEL` or switch to Groq vars.
2) Re-run `apps/cli/run_suite.py` (or your workflow) with a new `--run-name`.
3) Compare `cost_summary.json` files or AgentOps dashboard traces between runs.

## Notes
- All AgentOps calls are best-effort and fail-safe; missing API keys simply disable the sink.
- The sink is process-wide; a new run reinitializes the trace and totals.***
