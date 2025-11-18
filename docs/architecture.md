# Multi-Agent Hardware Design System: System Architecture

## Introduction

This architecture enables a two-phase flow—planning then execution—to produce verified HDL from a frozen design context. A human-supervised planning gate removes ambiguity up front; the execution phase then fans out tasks across agents and deterministic workers. For a gentle primer see [overview.md](./overview.md); for agent-level behavior see [agents.md](./agents.md).

## Logical Components

- **Orchestrator:** Owns the Design Context/DAG and artifact state machine; discovers ready work, publishes tasks, consumes results, and advances states. It does not execute tasks directly.  
- **Task Broker (RabbitMQ):** Durable message bus that decouples scheduling from execution. Provides queues for agent tasks, deterministic/process tasks, simulation tasks, a results queue, and DLX/DLQ routing. See [queues-and-workers.md](./queues-and-workers.md) for queue semantics.  
- **Agent Pool (LLM Agents):** Logical roles for Specification Helper, Planner, Implementation, Testbench, Reflection, and Debug. All run behind a single agent-worker runtime; behavior is detailed in [agents.md](./agents.md).  
- **Process/Simulation Pools (Deterministic Workers):** Deterministic executors for linting, compilation, distillation, and simulation. These use external toolchains and do not perform LLM reasoning.  
- **Data Stores:**  
  - **Design Context (read-only):** Frozen specification, interfaces, and DAG emitted after planning.  
  - **Task Memory (writeable):** Per-task artifacts (attempts, logs, distilled datasets, reflections, metrics) that enable retries and analysis.

## Runtime & Deployment Topology

The system is deployed as cooperating runtimes wired through RabbitMQ:

- **CLI runtime:** Thin client a user operates locally or in its own container; communicates with the Orchestrator/queues via HTTP/gRPC or broker APIs.  
- **Agent-worker runtime:** A generic service that hosts all LLM-based agents; agents are selected by `AgentType` on each task. Scale by adding replicas of this service.  
- **Deterministic-workers runtime:** Worker pool(s) for lint, compile, simulate, and distill tasks that run external toolchains.  
- **RabbitMQ runtime (Task Broker):** Dedicated broker instance providing `agent_tasks`, `process_tasks`, `simulation_tasks`, `results`, and DLQ routing.  
- **Data/Storage services:** Backing stores for Design Context and Task Memory as required by the deployment.

For single-user local mode these appear as separate services in one `docker-compose.yml` (optional `cli` service plus `agent-worker`, `deterministic-workers`, `rabbitmq`, and storage).

Agents never call each other directly; all work is mediated by the Orchestrator and brokered queues. Scaling is achieved by adding worker replicas rather than minting per-agent microservices.

## Phase Workflow (Planning vs Execution)

- **Planning Phase:** Human + Specification Helper Agent converge on the L1–L5 checklist, producing a frozen specification. The Planner Agent consumes it to emit the Design Context/DAG and frozen interfaces. Details live in [spec-and-planning.md](./spec-and-planning.md) and [agents.md](./agents.md).  
- **Execution Phase:** The Orchestrator scans the DAG for ready nodes, publishes tasks to the broker, workers execute, and results update state. Testing/analysis loops (distill → reflect → debug) ride the same queues; see [queues-and-workers.md](./queues-and-workers.md) for the lifecycle. The process repeats until acceptance criteria are met.

## Error Handling & Escalation (High-Level)

- Broker DLX/DLQ isolate poison-pill tasks without blocking healthy traffic.  
- Workers validate messages against schemas before running; unrecoverable failures are rejected to the DLQ.  
- Human escalation is triggered when retries stall or DLQ alerts fire; the Orchestrator packages context from Task Memory to speed triage.  
See [queues-and-workers.md](./queues-and-workers.md) for DLQ mechanics and [schemas.md](./schemas.md) for message invariants.
