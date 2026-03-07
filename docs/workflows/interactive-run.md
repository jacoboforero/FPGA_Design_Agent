# Interactive Run Workflow

## Purpose
Provide a practical runbook for interactive planning and execution.

## Audience
Developers running the full flow locally for iterative design work.

## Scope
End-to-end interactive run path from spec entry to execution output.

## Steps (from repo root)
```bash
make build
make up
make deps
make cli
```

## Host Fallback
```bash
PYTHONPATH=. python3 apps/cli/cli.py --timeout 120 --config config/runtime.yaml --preset engineer_fast
```

## Outputs to Inspect
- `artifacts/generated/`
- `artifacts/task_memory/`
- `artifacts/observability/`

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/cli.py`
- `/home/jacobo/school/FPGA_Design_Agent/Makefile`

## Related Docs
- [../cli.md](../cli.md)
- [failure-repair-loop.md](./failure-repair-loop.md)
