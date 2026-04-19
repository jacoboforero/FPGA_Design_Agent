# Tests Override

- Add tests in the package that mirrors the production code you changed.
- Prefer focused test targets while iterating; use broader suites only when the change crosses package boundaries.
- Keep reusable fixtures in `tests/fixtures/` and text specs in `tests/test_specs/` instead of embedding large inline blobs repeatedly.
- Avoid introducing network or Docker requirements into pure unit tests. Infrastructure coverage belongs under `tests/infrastructure/`.
- When docs or command examples change, run `python3 scripts/validate_docs.py` in addition to any affected Python tests.
