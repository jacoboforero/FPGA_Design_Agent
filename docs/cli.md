# CLI

## Purpose
Document the canonical command-line entrypoints and expected run patterns.

## Audience
Users and maintainers running the system locally or in containers.

## Scope
Command usage and operational notes. Internal orchestration logic is out of scope.

## Primary Entrypoint
- `apps/cli/cli.py`

## Recommended Containerized Flow (from repo root)
```bash
make build
make up
make deps
make cli
```

## Host Fallback (from repo root)
```bash
PYTHONPATH=. python3 apps/cli/cli.py --timeout 120 --config config/runtime.yaml --preset engineer_fast
```

## Useful Subcommands
```bash
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark
```

## Notes
- `benchmark` preset is for benchmark command usage, not interactive full flow.
- Runtime behavior is YAML-driven (`config/runtime.yaml`), while secrets remain env-based.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/cli.py`
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/doctor.py`
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/run_verilog_eval.py`

## Related Docs
- [workflows/interactive-run.md](./workflows/interactive-run.md)
- [workflows/benchmark-run.md](./workflows/benchmark-run.md)
- [reference/runtime-config.md](./reference/runtime-config.md)
