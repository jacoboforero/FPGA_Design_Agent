# Multi-Agent Hardware Design System: Overview

The system accelerates the digital hardware design lifecycle by combining rigorous upfront planning with automated execution. A frozen design context enables agents and deterministic workers to operate in parallel without re-litigating requirements.

## Vision

Deliver verified HDL from high-level intent with human control over decisive choices while automating the repetitive work of generating, testing, and refining artifacts.

## Core Principle

**Exhaustive upfront planning enables mechanical, parallel execution.** Once the specification and design graph are frozen, the system runs tasks independently across specialized workers.

## Phases at a Glance

- **Planning Phase:** Human + Specification Helper Agent converge on L1–L5, then the Planner Agent emits a frozen Design Context/DAG.  
- **Execution Phase:** The Orchestrator walks the DAG, enqueues tasks, workers execute, and results drive state transitions until acceptance criteria are met.

## Read Next

- System architecture and runtime topology: [architecture.md](./architecture.md)  
- Agent responsibilities and IO contracts: [agents.md](./agents.md)  
- Specification and planning checklist (L1–L5): [spec-and-planning.md](./spec-and-planning.md)  
- Queues, workers, DLQ/DLX details: [queues-and-workers.md](./queues-and-workers.md)  
- Message schemas and controlled vocabularies: [schemas.md](./schemas.md)
