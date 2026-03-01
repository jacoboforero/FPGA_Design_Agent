# Observability

## Purpose
Explain runtime event logging and LLM cost tracking outputs.

## Audience
Contributors diagnosing run behavior, comparing model costs, or auditing execution timelines.

## Scope
Local observability outputs and optional AgentOps integration.

## Outputs
- `artifacts/observability/<run_name>_events.jsonl`
- `artifacts/observability/costs.jsonl`
- `artifacts/observability/cost_summary.json`
- `artifacts/observability/runs/<run_name>/<run_id>/task_memory/`

## Usage Notes
- Run names can be provided via CLI for easier comparison.
- Logging is best-effort; missing AgentOps credentials should not break runtime execution.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/core/observability/`
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/cli.py`

## Related Docs
- [cli.md](./cli.md)
- [workflows/interactive-run.md](./workflows/interactive-run.md)
