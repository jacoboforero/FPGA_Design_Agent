# RabbitMQ Infrastructure

This directory contains the RabbitMQ infrastructure setup for the Multi-Agent Hardware Design System. The infrastructure provides a message broker that enables asynchronous task distribution and error handling.

## Files

- `docker-compose.yml` - RabbitMQ service configuration with Docker Compose
- `rabbitmq-definitions.json` - Queue, exchange, and binding definitions
- `rabbitmq.conf` - RabbitMQ configuration file (enables automatic definitions loading)
- `SETUP_NOTES.md` - Detailed setup and configuration documentation

## Quick Start

```bash
# Start RabbitMQ
cd infrastructure/
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs

# Stop service
docker-compose down
```

## Access

- **Management UI**: http://localhost:15672 (user/password)
- **AMQP**: localhost:5672

## Queue Architecture

The system uses a multi-queue architecture optimized for different task types:

### Task Queues

- **`agent_tasks`** - REASONING entity tasks (priority 1-3, supports priority ordering)
- **`process_tasks`** - LIGHT_DETERMINISTIC entity tasks (fast, deterministic)
- **`simulation_tasks`** - HEAVY_DETERMINISTIC entity tasks (long-running simulations)

### Error Handling

- **`dead_letter_queue`** - Failed/unprocessable tasks (quarantined for analysis)

### Exchanges

- **`tasks_exchange`** - Routes tasks to appropriate queues based on EntityType
- **`tasks_dlx`** - Dead Letter Exchange for routing failed tasks to DLQ

## Schema Integration

The queue routing keys align with `EntityType` enum values in `schemas/contracts.py`:

- `EntityType.REASONING` → routing key "REASONING" → queue "agent_tasks"
- `EntityType.LIGHT_DETERMINISTIC` → routing key "LIGHT_DETERMINISTIC" → queue "process_tasks"
- `EntityType.HEAVY_DETERMINISTIC` → routing key "HEAVY_DETERMINISTIC" → queue "simulation_tasks"

## Priority Support

The `agent_tasks` queue supports priority levels (1-3) that align with `TaskPriority` enum:

- `TaskPriority.LOW` = 1
- `TaskPriority.MEDIUM` = 2
- `TaskPriority.HIGH` = 3

## Automatic Configuration

The infrastructure automatically loads queue and exchange definitions on startup through:

1. **rabbitmq.conf** - Configures RabbitMQ to load definitions from JSON file
2. **Volume mounts** - Mounts configuration files into the container
3. **User creation** - Test fixtures automatically create required users

## Testing

Run the infrastructure tests to verify everything is working:

```bash
# From project root
python3 run_infrastructure_tests.py
```

All 28 tests should pass, confirming:

- ✅ RabbitMQ service starts correctly
- ✅ All queues and exchanges are properly configured
- ✅ Schema integration works seamlessly
- ✅ Message flow works end-to-end
- ✅ DLQ functionality is operational
