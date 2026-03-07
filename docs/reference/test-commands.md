# Test Commands Reference

## Purpose
Provide a quick command catalog for common test scopes.

## Audience
Developers and CI maintainers.

## Scope
Command quick reference only.

## Commands (from repo root)
```bash
pytest tests/core/schemas -q
pytest tests/infrastructure -q
pytest tests/workers -q
pytest tests/execution -q
python3 tests/run_infrastructure_tests.py
python3 tests/run_schema_tests.py
```

## Notes
- Use focused suites during development; reserve full-suite runs for broader validation.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/tests/`
- `/home/jacobo/school/FPGA_Design_Agent/pytest.ini`

## Related Docs
- [../test-plan.md](../test-plan.md)
- [../workflows/interactive-run.md](../workflows/interactive-run.md)
