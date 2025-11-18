# Multi-Agent Hardware Design System

## Overview

This project implements a sophisticated multi-agent system designed to accelerate the digital hardware design lifecycle. The system automates the generation, verification, and integration of hardware description language (HDL) artifacts, transforming high-level specifications into verified designs through a two-phase approach: exhaustive upfront planning followed by mechanical, parallel execution.

## System Architecture

The system is built on the principle that **exhaustive upfront planning enables mechanical, parallel execution**. It consists of four primary components:

- **Orchestrator**: Central "brain" that maintains the design graph state and determines task readiness
- **Task Broker**: RabbitMQ message bus with `agent_tasks`, `process_tasks`, `simulation_tasks`, `results`, and DLX/DLQ for fault tolerance
- **Worker Pools**: An agent-worker runtime hosting LLM agents (Specification Helper, Planner, Implementation, Testbench, Reflection, Debug) and deterministic workers for lint/compile/sim/distill
- **Data Stores**: Design context and task memory for state management

## Two-Phase Workflow

### Phase 1: Planning & Decomposition

- Human-designer collaboration with Planner agent
- Specification convergence (L1-L5 levels)
- DAG construction and interface definition
- Frozen design context as immutable source of truth

### Phase 2: Asynchronous Execution

- Fully automated orchestration
- Parallel task execution across worker pools
- State-driven progression through artifact lifecycle
- Human escalation for complex issues

## Key Features

- **Agent vs. Process Duality**: LLM-driven agents for creative tasks, deterministic processes for verification
- **Asynchronous Parallel Execution**: Maximized throughput through independent task processing
- **Fault Tolerance**: Dead Letter Queue system for handling unrecoverable failures
- **Human-in-the-Loop**: Strategic oversight and expert intervention when needed
- **State-Driven Progression**: Formal state machine for all artifacts (Stub → Draft → Testing → Passing → Frozen)

## Technology Stack

- **Multi-Agent Architecture**: Specialized agents for different design tasks
- **Message Queuing**: Asynchronous task distribution and result collection
- **HDL Generation**: SystemVerilog RTL and testbench generation
- **Simulation Integration**: EDA tool integration for verification
- **Schema-Driven**: Type-safe message contracts and validation

## Project Goals

- Accelerate hardware design from specification to verified RTL
- Demonstrate AI-driven automation of complex engineering workflows
- Provide scalable, fault-tolerant system architecture
- Enable parallel execution of independent design tasks
- Maintain human oversight for strategic decisions

## Development Setup

### RabbitMQ (Local Development)

The system uses RabbitMQ for asynchronous task distribution. To start the local development environment:

```bash
# Navigate to infrastructure directory
cd infrastructure/

# Start RabbitMQ with management UI
docker-compose up -d

# Verify the service is running
docker-compose ps
```

**Access Points:**

- **Management UI**: http://localhost:15672
  - Username: `user`
  - Password: `password`
- **AMQP Connection**: `localhost:5672`

**Configured Queues:**

- `agent_tasks` - LLM-based reasoning tasks (with 3-level priority)
- `process_tasks` - Light deterministic tasks
- `simulation_tasks` - Heavy deterministic tasks
- `dead_letter_queue` - Failed/unprocessable tasks

**To stop the service:**

```bash
docker-compose down
```

### Testing Infrastructure

The RabbitMQ setup includes comprehensive tests to ensure reliability:

```bash
# Run all infrastructure tests
python run_infrastructure_tests.py

# Quick health check
python run_infrastructure_tests.py --quick

# Run specific test categories
pytest tests/infrastructure/test_docker_setup.py -v
pytest tests/infrastructure/test_schema_integration.py -v
```

**Test Coverage:**

- ✅ Docker Compose setup and service health
- ✅ Queue configuration and bindings
- ✅ Schema integration with message routing
- ✅ End-to-end message flow
- ✅ Dead Letter Queue functionality

## Documentation

- **Overview**: High-level system tour in `docs/overview.md`
- **Architecture**: Runtime and logical design in `docs/architecture.md`
- **Agents**: Roles and responsibilities in `docs/agents.md`
- **Specification & Planning**: L1–L5 checklist in `docs/spec-and-planning.md`
- **Queues & Workers**: Broker/DLQ details in `docs/queues-and-workers.md`
- **Schemas**: Message contracts in `docs/schemas.md` and `schemas/SCHEMAS.md`
- **Testing**: Comprehensive test suite in `tests/` directory

---

_Developed by SD1 2025 Group 5_
