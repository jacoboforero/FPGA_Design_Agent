# Runtime Config Reference

## Purpose
Provide a concise reference for runtime YAML sections and policy ownership.

## Audience
Contributors updating configuration, defaults, and preset behavior.

## Scope
Reference summary only; implementation is authoritative in code.

## YAML Sections
- `active_preset`, `presets`
- `broker`
- `cli`
- `llm`
- `tools`
- `lint`
- `sim`
- `debug`
- `benchmark`

## Invocation Pattern (from repo root)
```bash
PYTHONPATH=. python3 apps/cli/cli.py --config config/runtime.yaml --preset engineer_fast
```

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/config/runtime.yaml`
- `/home/jacobo/school/FPGA_Design_Agent/core/runtime/config.py`

## Related Docs
- [../config-migration.md](../config-migration.md)
- [../cli.md](../cli.md)
