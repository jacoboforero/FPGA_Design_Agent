# Infrastructure Test Suite

## Purpose
Describe what infrastructure tests validate and how to run them.

## Audience
Contributors validating RabbitMQ behavior and schema-routing alignment.

## Scope
Infrastructure-only test behavior (not full pipeline correctness).

## Covered Areas
- Docker/compose bring-up validation
- Queue/exchange/binding correctness
- Schema-to-routing consistency
- Message flow and DLQ behavior

## Run Commands (from repo root)
```bash
python3 tests/run_infrastructure_tests.py
pytest tests/infrastructure -v
```

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/tests/infrastructure/`
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/rabbitmq-definitions.json`

## Related Docs
- [/home/jacobo/school/FPGA_Design_Agent/infrastructure/README.md](/home/jacobo/school/FPGA_Design_Agent/infrastructure/README.md)
- [/home/jacobo/school/FPGA_Design_Agent/docs/test-plan.md](/home/jacobo/school/FPGA_Design_Agent/docs/test-plan.md)
