# Infrastructure Test Suite

These tests validate RabbitMQ topology and broker behavior used by orchestrator and workers.

## Covered Areas
- Docker/compose broker bring-up.
- Queue/exchange/binding correctness.
- Message flow and DLQ routing behavior.
- Contract/routing alignment checks.

## Run Commands
From repo root:

```bash
python3 tests/run_infrastructure_tests.py
pytest tests/infrastructure -v
```

## Related Files
- `tests/infrastructure/`
- `infrastructure/rabbitmq-definitions.json`
- `infrastructure/docker-compose.yml`
