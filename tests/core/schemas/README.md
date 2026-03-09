# Schema Test Suite

These tests protect contract compatibility for task/result messages and planning schemas.

## Coverage Areas
- enum correctness
- model validation
- serialization/deserialization behavior
- L1-L5 specification schema behavior

## Run Commands
From repo root:

```bash
pytest tests/core/schemas -v
python3 tests/run_schema_tests.py
```

## Related Files
- `tests/core/schemas/`
- `core/schemas/`
- `docs/schemas.md`
