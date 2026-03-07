# Schema Test Suite

## Purpose
Document schema test coverage and execution commands.

## Audience
Contributors changing `core/schemas` contracts or validation behavior.

## Scope
Schema-focused tests and expected coverage domains.

## Coverage Areas
- enums
- model validation
- serialization/deserialization
- L1-L5 specification schema behavior

## Run Commands (from repo root)
```bash
pytest tests/core/schemas -v
python3 tests/run_schema_tests.py
```

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/tests/core/schemas/`
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/`

## Related Docs
- [/home/jacobo/school/FPGA_Design_Agent/docs/schemas.md](/home/jacobo/school/FPGA_Design_Agent/docs/schemas.md)
- [/home/jacobo/school/FPGA_Design_Agent/docs/test-plan.md](/home/jacobo/school/FPGA_Design_Agent/docs/test-plan.md)
