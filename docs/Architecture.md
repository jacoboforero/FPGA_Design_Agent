---

## Multi-Agent Hardware Design System: System Architecture

### 1.0 Introduction

### 1.1 Vision

This document specifies the architecture for a multi-agent system designed to accelerate the digital hardware design lifecycle. The system automates the generation, verification, and integration of hardware description language (HDL) artifacts, transforming high-level specifications into verified designs.

### 1.2 Core Principle

The architecture is founded on a single, guiding principle: **Exhaustive upfront planning enables mechanical, parallel execution.** By investing in a rigorous, human-supervised planning phase to produce a complete and immutable design graph, the subsequent implementation phase can be executed by agents with high efficiency, predictability, and parallelism.

### 1.3 Document Purpose

This document provides a definitive overview of the system's components, their responsibilities, their interactions, and the data flows between them. It is intended for architects, developers, and project stakeholders.

---

### 2.0 Guiding Architectural Principles

- **Planning Precedes Execution:** All creative, architectural, and ambiguous decisions are resolved before any implementation code is generated. The system is split into two distinct phases: Planning (strategic) and Execution (tactical).
- **Agent vs. Process Duality:** The system uses two fundamental primitives: **Agents** for tasks requiring reasoning, creativity, and generation (e.g., writing code, debugging, reflection), and **Processes** for deterministic, verifiable tasks (e.g., linting, compiling, running simulations, data distillation).
- **State-Driven Progression:** Every artifact (RTL module, testbench) exists within a formal state machine. Progress is defined as the transition of artifacts between these states: `Stub` → `Draft` → `Testing` → `Testing_Analysis` → `Passing` → `Frozen`.
- **Asynchronous, Parallel Execution:** The system is designed to maximize throughput by executing all independent tasks in parallel. An asynchronous queuing architecture decouples task scheduling from task execution. Within a state, multiple ordered subtasks may execute as a pipeline where required (e.g., analysis stages).
- **Human-in-the-Loop Escalation:** The system is not a fully autonomous black box. It relies on human oversight for initial planning approval and acts as a sophisticated assistant that escalates complex or ambiguous problems back to a human expert when its agents are stuck.

---

### 3.0 System Architecture Overview

The system is composed of four primary components: an Orchestrator, a Task Broker, a set of specialized Worker Pools, and a structured Data Store. To enhance resilience and isolate unrecoverable failures, the queuing subsystem includes a **Dead Letter Exchange (DLX)**, a **Dead Letter Queue (DLQ)**, and a **DLQ Monitor & Alerter**.

### 3.1 Component Diagram

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              PLANNING PHASE                                   │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌────────────────────┐        bidirectional guidance        ┌──────────────┐ │
│  │  HUMAN DESIGNER    │◄────────────────────────────────────►│ SPEC HELPER  │ │
│  │     (Architect)    │                                      │    AGENT     │ │
│  └────────────────────┘                                      └──────────────┘ │
│                                       │ finalize L1–L5                        │
│                                       ▼                                       │
│                          ┌────────────────────────────────┐                   │
│                          │         PLANNER AGENT          │                   │
│                          │ (Generates Design Context &    │                   │
│                          │       DAG from frozen spec)    │                   │
│                          └────────────────────────────────┘                   │
│                                       │                                       │
│                                       │  (Frozen Plan)                        │
│                                       ▼                                       │
└───────────────────────────────────────┴───────────────────────────────────────┘


┌───────────────────────────────────────────────────────────────────────────────┐
│                              EXECUTION PHASE                                  │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌────────────────────┐      state/context       ┌──────────────────────────┐ │
│  │  DESIGN CONTEXT    │◄────────────────────────►│       ORCHESTRATOR       │ │
│  │     (Read-only)    │                          │ (DAG state & task logic) │ │
│  └────────────────────┘                          └─────────────┬────────────┘ │
│                                                               publish tasks   │
│                                                               (per routing)   │
│                                        ┌────────────────────────┴───────────┐ │
│                                        │             TASK BROKER            │ │
│                                        │             (Message Bus)          │ │
│                                        │  routing keys:                     │ │
│                                        │   • agent_tasks                    │ │
│                                        │   • process_tasks                  │ │
│                                        │   • simulation_tasks               │ │
│                                        └───────────────┬─────────┬──────────┘ │
│                                                        │         │            │
│                                          consume/ack   │         │ consume/ack│
│            consume/ack                                   │         │          │
│  ┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│  │    AGENT POOL      │     │   PROCESS POOL     │     │  SIMULATION POOL   │ │
│  │ (LLM: impl/debug/  │     │ (lint/compile/     │     │   (long-running)   │ │
│  │  testgen/reflect)  │     │   distillation)    │     │                      │
│  └─────────┬──────────┘     └─────────┬──────────┘     └─────────┬──────────┘ │
│            │                          │                          │            │
│            │                          │                          │            │
│            └──────────────┬───────────┴───────────────┬──────────┘            │
│                           │                           │                       │
│                     ┌─────▼─────┐               ┌─────▼─────┐                 │
│                     │  RESULTS  │               │   DLX     │  (dead-letter   │
│                     │  QUEUE    │               │ (per-queue│   routing per   │
│                     └─────┬─────┘               │  exchange)│   broker config)│
│                           │                      └─────┬─────┘                │
│                 consume & │ update DAG                 │                      │
│                 ┌─────────▼─────────┐                 ▼                       │
│                 │    ORCHESTRATOR   │        ┌────────────────────┐           │
│                 └─────────┬─────────┘        │        DLQ         │           │
│                           │                   │ (quarantined msgs) │          │
│                           │ escalation        └─────────┬──────────┘          │
│                           ▼                             monitor               │
│                   ┌───────────────────┐                 │                     │
│                   │  HUMAN DESIGNER   │◄────────────────┘                     │
│                   │ (Expert helper &  │         alerts & investigation        │
│                   │   maintainer)     │                                       │
│                   └───────────────────┘                                       │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                           DATA STORES                                   │  │
│  │  • DESIGN CONTEXT (frozen spec, DAG, interfaces)                        │  │
│  │  • TASK MEMORY (per-task artifacts: attempts, logs,                     │  │
│  │    distilled datasets, reflection outputs, metadata)                    │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘

```

### 3.2 Component Descriptions

- **The Orchestrator:** The central "brain" of the system. It maintains the state of the entire design graph (DAG) but does not execute tasks itself. Its sole responsibilities are to monitor the state of design artifacts, determine which tasks are ready to run based on their dependencies, and publish those tasks to the Task Broker.
- **The Task Broker (Queuing System):** The central nervous system for communication. It is a message bus that decouples the Orchestrator from the workers. It manages dedicated queues for different types of work—**agent_tasks**, **process_tasks**, and **simulation_tasks**—ensuring that long-running tasks do not block short ones and that tasks are distributed efficiently to available workers.
- **Worker Pools:** Groups of independent processes that consume tasks from the queues and perform the actual work.

  - **Agent Pool:** Executes tasks requiring LLM-based intelligence (implementation, debugging, test generation, reflection). These workers are stateful during a task, leveraging short-term memory to learn from previous attempts.
  - **Process Pool:** Executes deterministic tasks like linting, compilation, and data distillation of waveforms/logs.
  - **Simulation Pool:** Executes slow, resource-intensive simulation tasks.

  **They are each individually responsible for identifying "poison pill" tasks and rejecting them to prevent infinite processing loops.**

- **Data Stores:** The system's memory.

  - **Design Context:** A read-only database containing the complete, frozen output of the planning phase including specifications and interfaces.
    **The DAG:** An optimized graph created by the planner to plan and track the entire execution process.
  - **Task Memory:** A writeable, structured store for each agent or process task, recording code attempts, test results, reflections, and multi-stage analysis artifacts to support debugging loops and data handoffs (distilled datasets, reflection outputs, and related metadata).

- **Dead Letter Exchange (DLX) & Dead Letter Queue (DLQ):** The dedicated routing and storage path for tasks that cannot be processed successfully. The DLX receives explicit rejections from workers and routes the corresponding messages to the DLQ for analysis.
- **DLQ Monitor & Alerter:** A monitoring component that tracks DLQ depth/age and notifies the Human Designer (System Maintainer) when intervention is required.

---

### 4.0 The Two-Phase Workflow

The system's operation is strictly divided into two phases. The transition from Planning to Execution is a hard gate that requires human approval.

### 4.1 Phase 1: Planning & Decomposition

This phase begins with collaboration between the human designer and a **Specification Helper Agent**, followed by automated decomposition by the **Planner Agent**.

1. **Specification Convergence (L1–L5):** The human provides high-level functional intent and iterates with the **Specification Helper Agent**. This agent asks clarifying questions, guides the human through the L1–L5 checklist (functional intent, interfaces, verification plan, constraints), and can propose edits to drafts upon request. The outcome of this step is a **frozen specification**.
2. **DAG Construction:** After the specification is frozen, the **Planner Agent** operates to translate the frozen specification into a directed acyclic graph (DAG) of modules and testbenches. Decomposition stops when each leaf node is a simple, implementable unit or a standard library component.
3. **Freezing the Plan:** The final output of the planning phase is the **Design Context**, which includes the complete DAG, all specifications, and all interfaces. This context is frozen and becomes the immutable "source of truth" for the execution phase.

**Outcome:** A complete, verifiable plan. No execution work has been done yet.

### 4.2 Phase 2: Asynchronous Execution

This phase is fully automated and driven by the Orchestrator and queuing system. It begins after a human approves the frozen Design Context.

The workflow is a continuous loop:

1. **Task Discovery:** The Orchestrator scans the DAG for any nodes whose dependencies are met and are ready to transition to a new state (e.g., a module in the `Stub` state is ready for an `implement` task).
2. **Task Publication:** For each ready node, the Orchestrator creates a task message and publishes it to the appropriate queue on the Task Broker.
3. **Task Consumption & Execution:** An available worker from the corresponding pool consumes the task and begins execution. This process is entirely independent of the Orchestrator and other workers.
4. **Result Notification:** Upon completion (success, failure, or need for help), the worker publishes a result message back to a central `results` queue.
5. **State Update & Iteration:** The Orchestrator consumes the result message, updates the artifact's state in the DAG, and the loop repeats. A successful implementation, for example, transitions a module to the `Draft` state, immediately making it eligible for a `test` task in the Orchestrator's next scan.

**Testing & Analysis Flow:**

- **Draft → Testing:** Standard test execution via Simulation and Process Pools.
- **Testing → Testing_Analysis:** On test failure, the artifact enters `Testing_Analysis` for a three-stage ordered pipeline:

  1. **Distillation (`distill` task):** Deterministic processing of waveforms/logs to extract failure-focused datasets. Dispatched via **process_tasks**.
  2. **Reflection (`reflect` task):** LLM-based analysis of distilled data to produce debugging hints, root-cause hypotheses, and investigation suggestions. Dispatched via **agent_tasks**.
  3. **Debugging (`debug` task):** Application of reflection insights to propose targeted code fixes. Dispatched via **agent_tasks**.

- **State Transitions:**

  - **Success Path:** `Testing_Analysis` → `Passing` (bug resolved and tests pass).
  - **Failure/Retry Path:** `Testing_Analysis` → `Testing` (re-run with new insights) or escalation to the Human Designer.

This cycle continues until the top-level node of the DAG reaches the `Passing` state and all acceptance criteria are met.

---

### 5.0 Deep Dive: The Queuing & Orchestration Subsystem

This subsystem is the engine of the execution phase. Its design is critical for achieving parallelism and resilience.

### 5.1 Rationale

A simple, greedy scheduler would lead to bottlenecks and fragility. The queuing architecture provides four key benefits:

- **Decoupling:** The Orchestrator doesn't need to know which worker is available or how to run a task. It only needs to announce that a task is ready. This simplifies the logic of all components.
- **Scalability:** To increase throughput, one only needs to add more workers to a pool. The architecture does not need to change.
- **Resilience & Load Balancing:** The queues act as a buffer. If a burst of tasks becomes ready, they are safely queued and processed as workers become available. If a worker crashes, the task can be safely re-queued and picked up by another worker.
- **Error Isolation (Fault Tolerance):** By decoupling producers and consumers and introducing dead-lettering, a single malformed or buggy task cannot halt an entire worker pool. Such tasks are isolated in the DLQ for later analysis, allowing healthy traffic to continue unhindered.

### 5.2 Task Lifecycle via Queues

1. **Creation:** The Orchestrator identifies a state transition (e.g., `Stub` → `Draft`) and creates a corresponding task.
2. **Dispatch:** The task is published to the appropriate queue (i.e., `agent_tasks`, `process_tasks`, or `simulation_tasks`) on the Task Broker.
3. **Execution:** A worker from the relevant pool consumes the task. The worker has exclusive ownership of this task until it is complete or explicitly rejected.
4. **Completion or Failure:** The worker completes its execution and publishes a result. On transient failures, standard retry/backoff policies apply (implementation-specific).
5. **Acknowledgement:** The Orchestrator processes the result, and the original task is permanently removed from the system. If the task failed and requires a retry or a different strategy, the Orchestrator will generate a _new_ task (e.g., a `debug` task or re-run `distill` after remediation).

### 5.3 Handling Unrecoverable Failures: The Dead Letter Queue

**Definition — "Poison Pill" Message:** Within this system, a poison pill is a `TaskMessage` that can never be successfully processed by its intended worker. Typical causes include:

- **Schema-Level Issues:** The message cannot pass basic validation against the schema contracts (e.g., invalid `EntityType`, missing required `context` fields), conflicting with the definitions in `contracts.py` (e.g., `TaskMessage`, enums such as `WorkerType`).
- **Deterministic, Irrecoverable Failures:** The message consistently triggers the same unrecoverable crash, assertion, or invariant violation in the worker despite retries (e.g., simulation setup irreparably inconsistent with the frozen Design Context).
- **Semantic Contradictions:** The payload requests an action that violates the frozen interface or verification plan, making forward progress impossible without human correction.

**DLX/DLQ Mechanism (Architectural Flow):**

1. **Detection:** Workers actively validate inputs and guard critical sections. When a worker concludes that a failure is not transient (e.g., fails schema validation, hits an invariant that cannot be relaxed, or exceeds a fixed retry threshold with identical root cause), it marks the task as **unrecoverable**.
2. **Rejection:** Instead of acknowledging the message, the worker **rejects** it (negatively acknowledges with `requeue=false` in typical broker semantics). This is a deliberate signal indicating that the message must not be returned to the main queue.
3. **Redirection via DLX:** The **Task Broker**, preconfigured with a **Dead Letter Exchange (DLX)** for each queue, automatically routes the rejected message—along with standard headers such as original routing key, rejection reason, and failure count—to the **Dead Letter Queue (DLQ)**.
4. **Isolation:** The message is quarantined in the DLQ and **cannot** block the primary queues or starve the worker pools. All other tasks continue to flow normally.
5. **Inspection & Remediation:** The **DLQ Monitor & Alerter** tracks DLQ depth, message age, and failure signatures. It notifies the **Human Designer (System Maintainer)** to investigate. Typical remediations include: fixing corrupt inputs, updating schemas or validation rules, adjusting orchestration logic, or manually replaying the corrected task.

**Operational Notes:**

- **Retention & Replay:** DLQ messages should retain headers (`task_id`, `correlation_id`, original routing key, first-failure timestamp, rejection reason) to support deterministic replay after remediation.
- **Metrics:** Emit counters for DLQ ingress rate, oldest message age, and top rejection reasons. Alerts should trigger on threshold breaches (e.g., age > SLO, surge in a specific failure signature).
- **Access Control:** DLQ read permissions are restricted to maintainers; write (requeue) operations are gated by change control to avoid reintroducing poison pills.

---

### 6.0 Human Interaction Model

The human designer is a critical part of the system, acting as the project lead and the ultimate authority.

- **Upfront Approval (The Architect):** The designer's primary role is to guide and approve the output of the planning phase. The quality of this initial plan directly determines the success of the execution phase.
- **On-Demand Intervention (The Expert & System Maintainer):** During execution, agents may become "stuck" on a task (e.g., repeated test failures). The Halting & Escalation logic in the Orchestrator will detect this, suspend that branch of the DAG, and generate a request for human help, packaged with all relevant context (code attempts, failure logs, agent analysis). **Additionally, the Human Designer serves as the System Maintainer responsible for investigating poison pill tasks that land in the DLQ.** The DLQ Monitor & Alerter notifies the human of critical items; the human performs root-cause analysis (schema mismatches, invariant violations, or contradictory specifications), applies corrections (schema/data fix, orchestration rule update), and, if appropriate, replays the sanitized task.
- **Analysis Escalation:** When analysis pipelines fail or stall, escalation bundles include the **complete analysis context** (distilled datasets, reflection outputs, failure signatures, retry counts, and timestamps) along with AI-suggested remediations.

This model ensures that agent creativity is applied to solving tractable problems, while strategic and deeply complex problem-solving—and systemic reliability—remain the responsibility of the human expert.

---

## Agent Definitions

Here are the exact agents that operate within the system, categorized by their phase of operation.

---

### Phase 1: Planning Agents

These agents operate exclusively during the initial, human-supervised planning phase. They are responsible for strategic decomposition and specification.

### **1. Specification Helper Agent**

- **Primary Goal:** To converge the hardware specification with the human designer through guided clarification and iterative drafting.
- **Inputs:**

  - Human-authored specification drafts and updates.

- **Outputs:**

  - A **frozen** L1–L5 specification ready for downstream planning.

- **Key Responsibilities:**

  - **Clarification Loop:** Ask targeted questions to remove ambiguity across functionality, interfaces, verification plan, and constraints.
  - **Draft Assistance:** Propose edits to the specification when requested by the human; integrate approved edits.
  - **Checklist Completion:** Ensure L1–L5 completeness prior to freeze.

### **2. The Planner Agent**

- **Primary Goal:** To translate the **frozen** specification into a complete, implementable Directed Acyclic Graph (DAG).
- **Inputs:**

  - The frozen L1–L5 specification.
  - The Standard Component Library definition.

- **Outputs:**

  - The **Design Context** containing the complete DAG of all modules, interfaces, and testbenches.

- **Key Responsibilities:**

  - **Architectural Decomposition:** Propose and refine the block hierarchy consistent with the frozen specification.
  - **Recursive Refinement:** Break down complex modules into manageable sub-modules until each leaf node is implementable or a standard component.
  - **Interface Propagation:** Define and finalize interfaces between all modules in the graph.

---

### Phase 2: Execution Agents

These agents are the workhorses of the automated execution phase. They are dispatched by the Orchestrator and operate in parallel to drive the artifacts through their state transitions.

### **3. The Implementation Agent**

- **Primary Goal:** To write synthesizable HDL code for a single module that correctly implements its frozen specification and adheres to its frozen interface.
- **Inputs:**

  - The specific module's specification.
  - The module's frozen interface contract (port names, widths, protocols).
  - Global design constraints (from the L5 checklist).

- **Outputs:**

  - A single, self-contained HDL file (e.g., `module.sv`).

- **Key Responsibilities:**

  - **Code Generation:** Translate the declarative specification into imperative RTL code, including state machines, data paths, and storage elements.
  - **Strict Adherence:** Creative freedom is strictly bounded by the provided interface; ports and protocols are immutable.

### **4. The Testbench Agent**

- **Primary Goal:** To write a verification environment (testbench) capable of stimulating a module and verifying its behavior against its verification plan.
- **Inputs:**

  - The target module's frozen interface.
  - The module's L3 Verification Plan (test scenarios, pass/fail criteria, coverage goals).

- **Outputs:**

  - A SystemVerilog testbench file.

- **Key Responsibilities:**

  - **Stimulus Generation:** Create logic to drive the module's inputs according to the scenarios in the verification plan.
  - **Oracle Implementation:** Write checking logic (e.g., scoreboards, assertions) to determine if the module's output is correct.
  - **Coverage Implementation:** Add constructs (covergroups, cover properties) to measure functional coverage as defined in the plan.

### **5. The Reflection Agent**

- **Primary Goal:** To analyze distilled waveforms and logs to produce debugging hints, root-cause hypotheses, and suggested investigation paths.
- **Inputs:**

  - Distilled datasets from the Distillation (Process) tasks.
  - Failure context (test descriptions, error messages, timestamps) and relevant design constraints.

- **Outputs:**

  - Structured insights (hypotheses, likely failure points, recommended probes) consumable by the Debug Agent.

- **Key Responsibilities:**

  - **AI-Powered Analysis:** Interpret failure-focused data to surface actionable insights.
  - **Guidance Artifacts:** Produce analysis notes attached to Task Memory for downstream debugging.

### **6. The Debug Agent**

- **Primary Goal:** To analyze a test failure, hypothesize the root cause, and propose a code modification to fix the bug, leveraging reflection insights when available.
- **Inputs:**

  - The failing HDL code.
  - The testbench that triggered the failure.
  - The simulation log and waveform summaries (distilled datasets).
  - Reflection outputs and the history of previous attempts and reflections from **Task Memory**.

- **Outputs:**

  - A _new version_ of the HDL code with a targeted fix applied.

- **Key Responsibilities:**

  - **Failure Analysis:** Parse provided artifacts to understand the exact symptom of the failure.
  - **Hypothesis Generation:** Form a theory about the underlying bug.
  - **Reflexion:** Review past attempts and reflection outputs to avoid repeating mistakes.
  - **Code Correction:** Implement a precise change to the code based on the hypothesis.

### Summary Table

| Agent                          | Phase     | Primary Input                     | Primary Output             | Core Function             |
| ------------------------------ | --------- | --------------------------------- | -------------------------- | ------------------------- |
| **Specification Helper Agent** | Planning  | Human Drafts                      | Frozen L1–L5 Specification | Specification Convergence |
| **Planner Agent**              | Planning  | Frozen L1–L5 Specification        | Design Context (DAG)       | Strategic Decomposition   |
| **Implementation Agent**       | Execution | Module Specification & Interface  | RTL Code (`.sv`)           | Code Generation           |
| **Testbench Agent**            | Execution | Verification Plan & Interface     | Testbench Code (`.sv`)     | Verification Generation   |
| **Reflection Agent**           | Execution | Distilled Data & Failure Context  | Debugging Insights         | AI-Powered Analysis       |
| **Debug Agent**                | Execution | Failing Code & Analysis Artifacts | Corrected RTL Code         | Targeted Bug Fixing       |

---

### 7.0 Alignment with Schemas (`contracts.py` / `SCHEMAS.md`)

- **Message Integrity:** All inter-component communication adheres to `TaskMessage` and `ResultMessage` models. Workers must validate inbound messages; failures at this stage are candidates for DLQ routing.
- **Traceability:** `task_id` and `correlation_id` are preserved in DLQ message headers to support post-mortem analysis and selective replay.
- **Controlled Vocabularies:** Enums such as `EntityType`, `AgentType`, and `WorkerType` are authoritative. Inconsistencies detected at ingestion should trigger rejection and dead-lettering.
- **Schema Extensions:**

  - New `AgentType` for **Specification Helper Agent** and **Reflection Agent**.
  - New `WorkerType` or subtype designation for **Distillation** tasks under the Process Pool (deterministic, heavy).
  - Enhanced context models to represent **multi-stage analysis handoffs** and **analysis metadata** (timestamps, failure signatures, retry counts, and upstream artifact references).

---

### 8.0 Non-Functional Requirements

- **Reliability:** DLQ isolation ensures poison pills cannot starve queues; SLOs defined on DLQ age and depth. Analysis pipelines include timeouts to prevent infinite loops.
- **Observability:** Metrics, logs, and traces capture DLX/DLQ events, rejection reasons, and replay outcomes. Track analysis pipeline performance (stage success rates, latency), data volume reductions from distillation, and insight utilization by debugging tasks.
- **Security:** Principle of least privilege for DLQ read/replay operations; audit trails for all requeues. Access controls apply to analysis artifacts stored in Task Memory.
- **Scalability:** Horizontal scaling of worker pools; DLQ capacity and monitoring thresholds scale with throughput. Distillation and reflection tasks share existing **process** and **agent** queues respectively; no additional queues are introduced.

---

### 9.0 Glossary

- **DLX (Dead Letter Exchange):** Broker component that routes rejected or expired messages to a DLQ.
- **DLQ (Dead Letter Queue):** Dedicated queue where un-processable messages are quarantined for analysis.
- **Poison Pill:** A message that cannot be successfully processed due to schema, invariant, or semantic violations.
- **Negative Acknowledgement (Reject):** Worker signal that a message must not be requeued to the primary queue.
- **Testing_Analysis:** A state entered after failed tests to run an ordered analysis pipeline (distill → reflect → debug) before proceeding to `Passing` or returning to `Testing`.
- **Distillation:** Deterministic reduction of large waveform/log datasets to failure-relevant summaries (dispatched via `process_tasks`).
- **Reflection:** LLM-based analysis of distilled datasets to produce debugging insights (dispatched via `agent_tasks`).

---
