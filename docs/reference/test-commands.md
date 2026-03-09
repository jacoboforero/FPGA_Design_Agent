# Test Commands Reference

Quick command set from repo root:

```bash
pytest tests/core/schemas -q
pytest tests/infrastructure -q
pytest tests/workers -q
pytest tests/execution -q
pytest tests/orchestrator -q
pytest tests/apps/test_run_verilog_eval.py -q
pytest tests/apps/test_run_benchmark_campaign.py -q
pytest tests/apps/test_index_runs.py -q
python3 tests/run_infrastructure_tests.py
python3 tests/run_schema_tests.py
python3 scripts/validate_docs.py
python3 scripts/validate_docs.py --run-commands
```

## Tips
- Use focused suites while iterating locally.
- Run broader integration suites before merging orchestrator/worker changes.
- Run `validate_docs.py` before doc-heavy changes to keep links and command examples trustworthy.
