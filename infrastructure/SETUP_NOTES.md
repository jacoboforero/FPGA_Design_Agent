# RabbitMQ Setup Notes

## Purpose
Capture detailed setup behavior and troubleshooting guidance for RabbitMQ in local development.

## Audience
Contributors diagnosing broker startup, bindings, or authentication issues.

## Scope
Detailed setup and troubleshooting only.

## Definitions Loading
RabbitMQ loads `infrastructure/rabbitmq-definitions.json` through `infrastructure/rabbitmq.conf`.

## Run and Verify (from repo root)
```bash
docker-compose -f infrastructure/docker-compose.yml up -d rabbitmq
python3 tests/run_infrastructure_tests.py
```

## Frequent Troubleshooting
- Definitions not loaded: verify mounted files in compose config.
- Authentication mismatch: verify configured user/pass and vhost permissions.
- Port conflicts: ensure `5672` and `15672` are free.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/rabbitmq.conf`
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/rabbitmq-definitions.json`
- `/home/jacobo/school/FPGA_Design_Agent/tests/infrastructure/`

## Related Docs
- [README.md](./README.md)
- [/home/jacobo/school/FPGA_Design_Agent/docs/architecture.md](/home/jacobo/school/FPGA_Design_Agent/docs/architecture.md)
