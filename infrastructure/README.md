# RabbitMQ Infrastructure

## Purpose
Document local RabbitMQ infrastructure setup and broker topology for this repository.

## Audience
Contributors running broker-dependent tests or local orchestration flows.

## Scope
Local development setup and verification commands.

## Services
- `rabbitmq`: message broker + management UI
- `app` (optional): pinned toolchain service for containerized workflows

## Quick Start (from repo root)
```bash
docker-compose -f infrastructure/docker-compose.yml up -d rabbitmq
```

## Management Endpoints
- Management UI: `http://localhost:15672`
- AMQP: `localhost:5672`

## Test Command (from repo root)
```bash
python3 tests/run_infrastructure_tests.py
```

## Routing Summary
- `REASONING` -> `agent_tasks`
- `LIGHT_DETERMINISTIC` -> `process_tasks`
- `HEAVY_DETERMINISTIC` -> `simulation_tasks`
- DLX -> `dead_letter_queue`

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/docker-compose.yml`
- `/home/jacobo/school/FPGA_Design_Agent/infrastructure/rabbitmq-definitions.json`
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/contracts.py`

## Related Docs
- [SETUP_NOTES.md](./SETUP_NOTES.md)
- [/home/jacobo/school/FPGA_Design_Agent/docs/queues-and-workers.md](/home/jacobo/school/FPGA_Design_Agent/docs/queues-and-workers.md)
