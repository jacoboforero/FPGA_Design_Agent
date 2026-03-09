# RabbitMQ Infrastructure

This folder defines the local RabbitMQ setup used by the pipeline and infrastructure tests.

## Services
- `rabbitmq`: broker + management UI.
- `app` (optional): pinned toolchain container for containerized workflows.

## Quick Start
From repo root:

```bash
docker-compose -f infrastructure/docker-compose.yml up -d rabbitmq
```

## Endpoints
- Management UI: `http://localhost:15672`
- AMQP: `localhost:5672`

## Verify With Tests
```bash
python3 tests/run_infrastructure_tests.py
```

## Related Files
- `infrastructure/docker-compose.yml`
- `infrastructure/rabbitmq-definitions.json`
- `infrastructure/SETUP_NOTES.md`
- `docs/queues-and-workers.md`
