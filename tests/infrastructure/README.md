# Infrastructure Tests

This directory contains comprehensive tests for the RabbitMQ infrastructure setup. These tests validate the **Task Broker** component that would support the Multi-Agent Hardware Design System.

## Test Overview

The tests simulate the **message queuing infrastructure** that would handle task distribution between the Orchestrator and Worker Pools. They do NOT test the actual AI agents or hardware design logic - only the messaging layer.

## Test Categories

### 1. Docker Setup Tests (`test_docker_setup.py`) - 5 tests ✅

**What they test**: Basic RabbitMQ service startup and configuration

- Docker Compose file validation
- Service startup and health checks
- Management UI accessibility (http://localhost:15672)
- AMQP connection testing
- Service health verification

### 2. Queue Configuration Tests (`test_queue_configuration.py`) - 5 tests ✅

**What they test**: Queue and exchange configuration matches the architecture

- Queue existence and configuration (`agent_tasks`, `process_tasks`, `simulation_tasks`, `dead_letter_queue`)
- Exchange setup and bindings (`tasks_exchange`, `tasks_dlx`)
- Priority configuration for `agent_tasks` (supports priorities 1-3)
- Dead Letter Exchange (DLX) setup and routing

### 3. Schema Integration Tests (`test_schema_integration.py`) - 7 tests ✅

**What they test**: Schema definitions align with RabbitMQ configuration

- EntityType enum alignment with routing keys
- TaskPriority enum alignment with RabbitMQ priorities (1-3)
- TaskMessage and ResultMessage serialization/deserialization
- Queue selection logic based on EntityType
- Priority mapping validation

### 4. Message Flow Tests (`test_message_flow.py`) - 5 tests ✅

**What they test**: Complete message publishing and consumption workflow

- End-to-end message publishing and consumption
- Priority message ordering (HIGH messages processed before LOW)
- Message persistence (survives broker restarts)
- Cross-queue message routing based on EntityType
- ResultMessage publishing back to system

### 5. DLQ Functionality Tests (`test_dlq_functionality.py`) - 6 tests ✅

**What they test**: Dead Letter Queue system for handling failed tasks

- Dead Letter Queue setup and configuration
- Message rejection simulation (poison pill handling)
- DLQ message format validation with metadata headers
- Monitoring capabilities for failed task analysis
- Error isolation and quarantine functionality

## Running Tests

### Prerequisites

```bash
# Install additional dependencies for testing
pip install pika requests pyyaml
```

### Run All Infrastructure Tests

```bash
# From project root - recommended method
python3 run_infrastructure_tests.py

# Alternative: direct pytest
pytest tests/infrastructure/ -v
```

### Run Specific Test Categories

```bash
# Docker setup only
pytest tests/infrastructure/test_docker_setup.py -v

# Queue configuration only
pytest tests/infrastructure/test_queue_configuration.py -v

# Schema integration only
pytest tests/infrastructure/test_schema_integration.py -v

# Message flow only
pytest tests/infrastructure/test_message_flow.py -v

# DLQ functionality only
pytest tests/infrastructure/test_dlq_functionality.py -v
```

### Run with Coverage

```bash
pytest tests/infrastructure/ --cov=infrastructure --cov-report=term-missing
```

## Test Fixtures

### `rabbitmq_service`

- Starts RabbitMQ service using docker-compose
- Waits for service to be ready (up to 60 seconds)
- Automatically creates required user (user/password)
- Automatically stops service after tests

### `rabbitmq_connection`

- Provides AMQP connection to RabbitMQ
- Uses credentials: user/password
- Automatically closes connection after tests

### `rabbitmq_channel`

- Provides AMQP channel for operations
- Automatically closes channel after tests

## Test Data

Tests use the existing schema models from `schemas/contracts.py`:

- **`TaskMessage`** with various `EntityType` and `TaskPriority` values
- **`ResultMessage`** with different `TaskStatus` outcomes
- **Realistic context data** for hardware design tasks
- **Priority mapping** (LOW=1, MEDIUM=2, HIGH=3)
- **EntityType routing** (REASONING → agent_tasks, etc.)

## Current Test Status

**All 28/28 tests passing (100%)** ✅

- **Docker Setup**: 5/5 tests ✅
- **Queue Configuration**: 5/5 tests ✅
- **Schema Integration**: 7/7 tests ✅
- **Message Flow**: 5/5 tests ✅
- **DLQ Functionality**: 6/6 tests ✅

## What the Tests Validate

The tests confirm that the **Task Broker infrastructure** is ready to support:

1. ✅ **Automatic startup** - RabbitMQ starts with all queues/exchanges configured
2. ✅ **Message routing** - Tasks get routed to correct queues based on EntityType
3. ✅ **Priority handling** - HIGH priority tasks processed before LOW priority
4. ✅ **Error isolation** - Failed tasks quarantined in DLQ without blocking healthy traffic
5. ✅ **Schema compatibility** - TaskMessage/ResultMessage serialization works seamlessly
6. ✅ **Persistence** - Messages survive broker restarts
7. ✅ **Monitoring** - DLQ provides visibility into failed tasks

## Troubleshooting

### Common Issues

1. **Docker not running**: Ensure Docker is installed and running
2. **Port conflicts**: Check that ports 5672 and 15672 are available
3. **Permission issues**: Ensure user has Docker permissions
4. **Service startup time**: Tests wait up to 60 seconds for RabbitMQ to be ready
5. **User authentication**: Tests automatically create user/password credentials

### Debug Mode

```bash
# Run with verbose output
pytest tests/infrastructure/ -v -s

# Run single test with debug
pytest tests/infrastructure/test_docker_setup.py::TestDockerSetup::test_management_ui_accessible -v -s

# Check RabbitMQ logs
cd infrastructure/
docker-compose logs rabbitmq
```

### Manual Verification

```bash
# Start infrastructure manually
cd infrastructure/
docker-compose up -d

# Check Management UI
open http://localhost:15672

# Test AMQP connection
python3 -c "import pika; conn = pika.BlockingConnection(pika.ConnectionParameters('localhost', 5672, '/', pika.PlainCredentials('user', 'password'))); print('Connection successful!'); conn.close()"
```
