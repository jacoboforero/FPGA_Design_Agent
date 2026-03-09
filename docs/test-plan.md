# Test Plan

The test strategy prioritizes contract correctness, orchestration behavior, execution-stage reliability, and documentation trust.

## Priority Coverage Areas
- Schema and enum validation.
- Planner/spec flow behavior.
- Orchestrator state transitions and dependency handling.
- Worker behavior (lint, TB lint, simulation, acceptance, distillation).
- Broker topology, routing, and DLQ plumbing.
- Benchmark command behavior and failure handling.
- Documentation quality guardrails (link integrity and command-smoke validation).

## Recommended Command Set
From repo root:

```bash
pytest tests/core/schemas -q
pytest tests/infrastructure -q
pytest tests/workers -q
pytest tests/execution -q
pytest tests/orchestrator -q
pytest tests/apps/test_run_verilog_eval.py -q
pytest tests/apps/test_run_benchmark_campaign.py -q
pytest tests/apps/test_index_runs.py -q
python3 scripts/validate_docs.py
python3 scripts/validate_docs.py --run-commands
```

## CI Guidance
- Keep schema/unit suites in fast default CI.
- Run heavier integration and benchmark-adjacent suites in staged or optional jobs.
- Include docs link validation in standard CI.
- Include docs command-smoke validation in scheduled/nightly or pre-release CI where runtime dependencies are available.

## Related Code
- `tests/`
- `pytest.ini`
- `apps/cli/run_validation_report.py`
- `scripts/validate_docs.py`
