# Test Plan

## Purpose
Describe test strategy, priority checks, and practical commands for routine verification.

## Audience
Contributors validating runtime behavior, broker routing, and schema correctness.

## Scope
Test planning and command references for local and CI usage.

## Priority Coverage
- Schema and contract tests
- Orchestration state progression and failure handling
- Worker behavior (lint, tb_lint, sim, acceptance, distill)
- Infrastructure routing and DLQ behavior

## Recommended Commands (from repo root)
```bash
pytest tests/core/schemas -q
pytest tests/infrastructure -q
pytest tests/workers -q
pytest tests/execution -q
python3 tests/run_infrastructure_tests.py
```

## CI Guidance
- Keep fast schema/unit checks in default CI path.
- Run tool-heavy and benchmark checks in optional jobs.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/tests/`
- `/home/jacobo/school/FPGA_Design_Agent/pytest.ini`

## Related Docs
- [reference/test-commands.md](./reference/test-commands.md)
- [workflows/failure-repair-loop.md](./workflows/failure-repair-loop.md)
