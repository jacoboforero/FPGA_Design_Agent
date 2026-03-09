# RabbitMQ Setup Notes

Detailed setup and troubleshooting notes for local broker startup.

## Definitions Loading
RabbitMQ loads `infrastructure/rabbitmq-definitions.json` through `infrastructure/rabbitmq.conf`.

## Run And Verify
From repo root:

```bash
docker-compose -f infrastructure/docker-compose.yml up -d rabbitmq
python3 tests/run_infrastructure_tests.py
```

## Common Troubleshooting
- Definitions not loaded: check file mounts in compose config.
- Authentication mismatch: verify user/password/vhost permissions.
- Port conflicts: make sure `5672` and `15672` are free.

## Related Files
- `infrastructure/rabbitmq.conf`
- `infrastructure/rabbitmq-definitions.json`
- `tests/infrastructure/`
