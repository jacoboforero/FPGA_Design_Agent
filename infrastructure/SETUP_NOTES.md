# RabbitMQ Infrastructure Setup Notes

## Overview

This document describes the RabbitMQ infrastructure setup for the Multi-Agent Hardware Design System, including configuration details and how automatic definitions loading works.

## Files

- `docker-compose.yml` - RabbitMQ service configuration with Docker Compose
- `rabbitmq-definitions.json` - Queue, exchange, and binding definitions
- `rabbitmq.conf` - RabbitMQ configuration file that enables automatic definitions loading

## Configuration Details

### Automatic Definitions Loading

The RabbitMQ instance is configured to automatically load queue, exchange, and binding definitions on startup through:

1. **rabbitmq.conf**: Contains the directive to load definitions from a JSON file

   ```
   management.load_definitions = /etc/rabbitmq/definitions.json
   ```

2. **Volume Mounts**: The docker-compose.yml mounts both configuration files:

   - `./rabbitmq-definitions.json:/etc/rabbitmq/definitions.json`
   - `./rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf`

3. **User Creation**: Since the definitions file creates the vhost, the `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS` environment variables are bypassed. Users must be created after the service starts (handled automatically in tests).

### Queue Structure

The following queues are automatically created on startup:

- **agent_tasks** - REASONING entity tasks (with 3-level priority support)

  - x-max-priority: 3
  - x-dead-letter-exchange: tasks_dlx

- **process_tasks** - LIGHT_DETERMINISTIC entity tasks

  - x-dead-letter-exchange: tasks_dlx

- **simulation_tasks** - HEAVY_DETERMINISTIC entity tasks

  - x-dead-letter-exchange: tasks_dlx

- **dead_letter_queue** - Failed/unprocessable tasks
  - No special arguments

### Exchange Structure

- **tasks_exchange** (direct) - Main exchange for routing tasks to appropriate queues
- **tasks_dlx** (fanout) - Dead Letter Exchange for failed messages

### Bindings

| Source Exchange | Routing Key         | Destination Queue | Type  |
| --------------- | ------------------- | ----------------- | ----- |
| tasks_exchange  | REASONING           | agent_tasks       | queue |
| tasks_exchange  | LIGHT_DETERMINISTIC | process_tasks     | queue |
| tasks_exchange  | HEAVY_DETERMINISTIC | simulation_tasks  | queue |
| tasks_dlx       | (any)               | dead_letter_queue | queue |

## Test Infrastructure

The test suite includes comprehensive validation for:

✅ **Docker Setup** (5/5 tests)

- Service startup and configuration
- Management UI accessibility
- AMQP connection testing

✅ **Queue Configuration** (5/5 tests)

- Queue existence and properties
- Exchange setup and bindings
- Dead Letter Exchange configuration

✅ **Schema Integration** (7/7 tests)

- EntityType enum alignment with routing keys
- TaskPriority mapping to RabbitMQ priorities
- Message serialization compatibility

✅ **Message Flow** (5/5 tests)

- End-to-end message publishing and consumption
- Priority message ordering
- Message persistence

✅ **DLQ Functionality** (6/6 tests)

- Dead Letter Queue setup
- Message rejection handling
- DLQ monitoring capabilities

## Running Tests

```bash
# Run all infrastructure tests
python run_infrastructure_tests.py

# Run specific test categories
pytest tests/infrastructure/test_docker_setup.py -v
pytest tests/infrastructure/test_schema_integration.py -v
pytest tests/infrastructure/test_queue_configuration.py -v
pytest tests/infrastructure/test_message_flow.py -v
pytest tests/infrastructure/test_dlq_functionality.py -v
```

## Manual Operations

### Start RabbitMQ

```bash
cd infrastructure/
docker-compose up -d
```

### Stop RabbitMQ

```bash
cd infrastructure/
docker-compose down
```

### View Logs

```bash
cd infrastructure/
docker-compose logs -f rabbitmq
```

### Management UI

- URL: http://localhost:15672
- Default credentials: user/password (for local dev only)

## Troubleshooting

### Issue: Definitions not loading

**Symptom**: Queues and exchanges don't exist after startup

**Solution**: Ensure both `rabbitmq-definitions.json` and `rabbitmq.conf` are properly mounted in docker-compose.yml

### Issue: Authentication failures

**Symptom**: Connection refused with authentication error

**Solution**: Create user manually after service starts:

```bash
docker exec multi-agent-task-broker rabbitmqctl add_user user password
docker exec multi-agent-task-broker rabbitmqctl set_user_tags user administrator
docker exec multi-agent-task-broker rabbitmqctl set_permissions -p / user ".*" ".*" ".*"
```

(This is handled automatically in the test fixtures)

### Issue: Port conflicts

**Symptom**: Cannot start service, ports already in use

**Solution**: Ensure ports 5672 (AMQP) and 15672 (Management UI) are not in use by other applications

## Production Considerations

⚠️ **Important**: The current setup is for LOCAL DEVELOPMENT ONLY

For production deployment:

1. Use secure credentials (not "user"/"password")
2. Enable TLS for AMQP connections
3. Configure proper authentication and authorization
4. Set up monitoring and alerting
5. Configure cluster mode for high availability
6. Use persistent volumes for data storage

## Schema Alignment

The queue routing keys align perfectly with the `EntityType` enum in `schemas/contracts.py`:

- `EntityType.REASONING` → routing key "REASONING" → queue "agent_tasks"
- `EntityType.LIGHT_DETERMINISTIC` → routing key "LIGHT_DETERMINISTIC" → queue "process_tasks"
- `EntityType.HEAVY_DETERMINISTIC` → routing key "HEAVY_DETERMINISTIC" → queue "simulation_tasks"

TaskPriority values (1-3) map directly to RabbitMQ priority levels, with the `agent_tasks` queue supporting priorities 1 (LOW), 2 (MEDIUM), and 3 (HIGH).
