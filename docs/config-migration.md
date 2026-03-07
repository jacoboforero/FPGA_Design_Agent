# Runtime Config Migration

## Purpose
Clarify YAML-vs-environment responsibilities after runtime configuration migration.

## Audience
Contributors changing configuration behavior or deployment setup.

## Scope
Configuration ownership boundaries and practical invocation examples.

## Ownership
- YAML (`config/runtime.yaml`): runtime behavior, presets, routing, policies
- Environment variables: secrets/credentials and selected compatibility overrides

## Example Commands (from repo root)
```bash
PYTHONPATH=. python3 apps/cli/cli.py --config config/runtime.yaml --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py benchmark --config config/runtime.yaml --preset benchmark
```

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/core/runtime/config.py`
- `/home/jacobo/school/FPGA_Design_Agent/config/runtime.yaml`

## Related Docs
- [reference/runtime-config.md](./reference/runtime-config.md)
- [cli.md](./cli.md)
