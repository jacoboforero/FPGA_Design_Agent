# Multi-Agent Hardware Design System: Agent Architecture

## Table of Contents

1. [Overview](#overview)
2. [Planning Phase Agents](#planning-phase-agents)
3. [Execution Phase Agents](#execution-phase-agents)
4. [Agent Interaction Patterns](#agent-interaction-patterns)
5. [Agent State Management](#agent-state-management)
6. [Error Handling & Escalation](#error-handling--escalation)

---

## Overview

This document provides detailed architectural descriptions of each agent within the Multi-Agent Hardware Design System. The system operates in two distinct phases: **Planning** (human-supervised strategic decomposition) and **Execution** (automated tactical implementation). Each agent is designed with specific responsibilities, input/output contracts, and interaction patterns.

The agents are categorized by their operational phase:

- **Planning Agents**: Strategic decomposition and specification
- **Execution Agents**: Tactical implementation and verification

---

## Planning Phase Agents

### 1. Specification Helper Agent

**Phase**: Planning  
**Primary Role**: Human-AI Collaboration Interface  
**Operational Mode**: Interactive, conversational

#### Architecture

The Specification Helper Agent serves as the primary interface between human designers and the automated system. It operates through an iterative, conversational workflow designed to converge on a complete and unambiguous hardware specification.

#### Core Responsibilities

1. **Specification Convergence**

   - Guide human designers through the L1-L5 specification checklist
   - Ask targeted clarifying questions to eliminate ambiguity
   - Ensure completeness across all specification dimensions

2. **Draft Assistance**

   - Propose edits to specification drafts upon request
   - Integrate approved changes into the evolving specification
   - Maintain version control and change tracking

3. **Quality Assurance**
   - Validate specification completeness against L1-L5 criteria
   - Identify gaps, contradictions, or unclear requirements
   - Ensure all interfaces, constraints, and verification plans are defined

#### Input/Output Contracts

**Inputs:**

- Human-authored specification drafts
- Clarification requests and responses
- Edit proposals and approvals

**Outputs:**

- Frozen L1-L5 specification
- Change history and decision rationale
- Validation reports and completeness assessments

#### Interaction Patterns

- **Bidirectional Communication**: Maintains active dialogue with human designer
- **Iterative Refinement**: Cycles through draft → review → edit → validation
- **Context Preservation**: Maintains conversation history and decision context
- **Escalation**: Can request human expert intervention for complex decisions

#### State Management

- **Active Session**: Maintains conversation state and draft versions
- **Validation State**: Tracks completion status of L1-L5 criteria

---

### 2. Planner Agent

**Phase**: Planning  
**Primary Role**: Strategic Decomposition  
**Operational Mode**: Automated, batch processing

#### Architecture

The Planner Agent operates as an automated decomposition engine that translates frozen specifications into implementable design graphs. It performs recursive architectural decomposition until all leaf nodes represent either implementable units or standard library components.

#### Core Responsibilities

1. **Architectural Decomposition**

   - Analyze frozen specification to identify major functional blocks
   - Propose hierarchical module structure
   - Define module boundaries and responsibilities

2. **Recursive Refinement**

   - Break down complex modules into manageable sub-modules
   - Continue decomposition until leaf nodes are implementable
   - Identify opportunities for standard component reuse

3. **Interface Definition**
   - Define and finalize interfaces between all modules
   - Ensure interface consistency across the design hierarchy
   - Propagate interface constraints from specification

#### Input/Output Contracts

**Inputs:**

- Frozen L1-L5 specification
- Standard Component Library definitions
- Design constraints and requirements

**Outputs:**

- Complete Design Context (DAG)
- Module specifications with frozen interfaces
- Implementation dependencies and ordering

#### Interaction Patterns

- **Batch Processing**: Operates on complete, frozen specifications
- **Deterministic Output**: Produces consistent DAG for identical inputs
- **Validation**: Ensures all generated interfaces are consistent and implementable
- **Documentation**: Generates comprehensive design context documentation

#### State Management

- **Decomposition State**: Tracks current level of decomposition
- **Interface State**: Manages interface definition and validation

---

## Execution Phase Agents

### 3. Implementation Agent

**Phase**: Execution  
**Primary Role**: RTL Code Generation  
**Operational Mode**: Task-driven, stateful

#### Architecture

The Implementation Agent is responsible for generating synthesizable HDL code for individual modules. It operates with strict adherence to frozen interfaces while applying creative problem-solving to implement functional requirements.

#### Core Responsibilities

1. **Code Generation**

   - Translate declarative specifications into imperative RTL code
   - Implement state machines, data paths, and storage elements
   - Generate synthesizable, optimized HDL

2. **Interface Adherence**

   - Strictly follow frozen interface contracts
   - Maintain port names, widths, and protocols as specified
   - Ensure compatibility with upstream and downstream modules

3. **Design Quality**
   - Apply coding standards and best practices
   - Optimize for synthesis and timing closure
   - Ensure code readability and maintainability

#### Input/Output Contracts

**Inputs:**

- Module specification and requirements
- Frozen interface contract (ports, protocols)
- Global design constraints (timing, area, power)
- Design context and dependencies

**Outputs:**

- Single, self-contained HDL file (e.g., `module.sv`)
- Implementation documentation and notes
- Synthesis and timing reports

#### Interaction Patterns

- **Task-Driven**: Responds to implementation tasks from Orchestrator
- **Stateful Processing**: Maintains context during complex implementations
- **Iterative Refinement**: Can receive feedback and generate improved versions
- **Validation**: Performs self-validation against interface contracts

#### State Management

- **Implementation State**: Tracks progress through code generation phases
- **Validation State**: Maintains validation status and error reports

---

### 4. Testbench Agent

**Phase**: Execution  
**Primary Role**: Verification Environment Generation  
**Operational Mode**: Task-driven, template-based

#### Architecture

The Testbench Agent generates comprehensive verification environments capable of stimulating modules and verifying their behavior against specified verification plans. It creates both stimulus generation and checking logic.

#### Core Responsibilities

1. **Stimulus Generation**

   - Create logic to drive module inputs according to verification scenarios
   - Implement test patterns and sequences from verification plan
   - Generate comprehensive input coverage

2. **Oracle Implementation**

   - Write checking logic (scoreboards, assertions) to verify correctness
   - Implement pass/fail criteria from verification plan
   - Create reference models where necessary

3. **Coverage Implementation**
   - Add functional coverage constructs (covergroups, cover properties)
   - Implement coverage goals from verification plan
   - Ensure comprehensive verification coverage

#### Input/Output Contracts

**Inputs:**

- Target module's frozen interface
- L3 Verification Plan (scenarios, criteria, coverage goals)
- Test requirements and constraints

**Outputs:**

- SystemVerilog testbench file
- Test configuration and parameters
- Coverage analysis setup

#### Interaction Patterns

- **Template-Based**: Uses verification templates and patterns
- **Scenario-Driven**: Implements specific test scenarios from verification plan
- **Coverage-Focused**: Prioritizes comprehensive verification coverage
- **Validation**: Ensures testbench correctness and completeness

#### State Management

- **Generation State**: Tracks testbench generation progress
- **Validation State**: Maintains testbench validation status

---

### 5. Reflection Agent

**Phase**: Execution  
**Primary Role**: AI-Powered Failure Analysis  
**Operational Mode**: Analysis-driven, insight generation

#### Architecture

The Reflection Agent performs sophisticated analysis of distilled waveforms and logs to produce actionable debugging insights. It leverages AI capabilities to identify patterns, hypothesize root causes, and suggest investigation paths.

#### Core Responsibilities

1. **AI-Powered Analysis**

   - Interpret failure-focused data from distillation processes
   - Identify patterns and anomalies in waveforms and logs
   - Generate hypotheses about root causes and failure mechanisms

2. **Insight Generation**

   - Produce structured debugging insights and recommendations
   - Suggest specific investigation paths and probe points
   - Create analysis notes for downstream debugging processes

3. **Context Integration**
   - Incorporate failure context (test descriptions, error messages)
   - Consider design constraints and requirements
   - Maintain analysis history and learning from previous failures

#### Input/Output Contracts

**Inputs:**

- Distilled datasets from distillation processes
- Failure context (test descriptions, error messages, timestamps)
- Design constraints and requirements
- Previous analysis history

**Outputs:**

- Structured insights and hypotheses
- Recommended investigation paths
- Analysis notes and debugging guidance

#### Interaction Patterns

- **Analysis-Driven**: Responds to analysis requests with insights
- **Learning-Based**: Incorporates lessons from previous analyses
- **Context-Aware**: Considers full failure context and design constraints
- **Collaborative**: Works with Debug Agent to provide targeted insights

#### State Management

- **Analysis State**: Tracks current analysis progress and findings
- **Learning State**: Maintains knowledge from previous analyses

---

### 6. Debug Agent

**Phase**: Execution  
**Primary Role**: Targeted Bug Fixing  
**Operational Mode**: Problem-solving, iterative

#### Architecture

The Debug Agent analyzes test failures, hypothesizes root causes, and proposes targeted code modifications to fix bugs. It leverages insights from the Reflection Agent and maintains awareness of previous debugging attempts.

#### Core Responsibilities

1. **Failure Analysis**

   - Parse failing HDL code and testbench
   - Analyze simulation logs and waveform summaries
   - Understand exact symptoms and failure mechanisms

2. **Hypothesis Generation**

   - Form theories about underlying bugs and root causes
   - Consider multiple failure scenarios and possibilities
   - Prioritize most likely causes based on evidence

3. **Code Correction**

   - Implement precise changes based on hypotheses
   - Apply targeted fixes to address root causes
   - Ensure fixes don't introduce new issues

4. **Learning Integration**
   - Review past attempts and reflection outputs
   - Avoid repeating previous mistakes
   - Incorporate lessons learned from similar failures

#### Input/Output Contracts

**Inputs:**

- Failing HDL code and testbench
- Simulation logs and waveform summaries
- Reflection outputs and analysis insights
- Previous debugging attempts and history

**Outputs:**

- New version of HDL code with targeted fixes
- Debugging rationale and change explanations
- Updated implementation documentation

#### Interaction Patterns

- **Problem-Solving**: Focuses on specific failure resolution
- **Iterative**: Can generate multiple fix attempts
- **Learning-Based**: Incorporates insights from Reflection Agent
- **Validation**: Ensures fixes address root causes without side effects

#### State Management

- **Debug State**: Tracks current debugging progress and attempts
- **Learning State**: Maintains knowledge from previous debugging sessions

---

## Agent Interaction Patterns

### Planning Phase Interactions

1. **Human ↔ Specification Helper Agent**

   - Interactive dialogue for specification convergence
   - Iterative refinement of requirements and constraints
   - Collaborative decision-making and approval workflow

2. **Specification Helper Agent → Planner Agent**
   - Handoff of frozen specification
   - Transfer of complete requirements and constraints
   - Initiation of automated decomposition process

### Execution Phase Interactions

1. **Orchestrator → Implementation Agent**

   - Task dispatch for module implementation
   - Context and requirements delivery
   - Progress monitoring and result collection

2. **Orchestrator → Testbench Agent**

   - Verification task assignment
   - Interface and verification plan delivery
   - Testbench validation and integration

3. **Reflection Agent → Debug Agent**

   - Insight delivery for debugging guidance
   - Analysis results and recommendations
   - Context sharing for targeted fixes

4. **All Agents → Task Memory**
   - Artifact storage and retrieval
   - Context preservation across tasks
   - Learning and knowledge accumulation

---

## Agent State Management

### State Persistence

Each agent maintains state across task executions to support:

- **Learning**: Accumulating knowledge from previous tasks
- **Context**: Preserving relevant information for current tasks
- **History**: Tracking attempts, successes, and failures

### State Synchronization

- **Task Memory**: Centralized state storage for all agents
- **Orchestrator**: Coordinates state transitions across agents
- **Context Sharing**: Agents can access relevant state from other agents

---

## Error Handling & Escalation

### Error Detection

Agents implement comprehensive error detection:

- **Input Validation**: Schema and contract validation
- **Process Monitoring**: Task execution and progress tracking
- **Output Verification**: Result quality and correctness checking

### Escalation Mechanisms

1. **Automatic Retry**: Transient failures with retry logic
2. **Agent Escalation**: Complex problems requiring different agent
3. **Human Escalation**: Problems requiring human intervention
4. **DLQ Routing**: Unrecoverable failures for analysis

### Error Recovery

- **Graceful Degradation**: Continue operation despite partial failures
- **Context Preservation**: Maintain state for recovery attempts
- **Learning Integration**: Incorporate error lessons into future tasks

---

## Summary

The Multi-Agent Hardware Design System employs six specialized agents operating across two phases:

**Planning Phase:**

- **Specification Helper Agent**: Human-AI collaboration for requirement convergence
- **Planner Agent**: Automated strategic decomposition and DAG generation

**Execution Phase:**

- **Implementation Agent**: RTL code generation with interface adherence
- **Testbench Agent**: Verification environment creation and coverage implementation
- **Reflection Agent**: AI-powered failure analysis and insight generation
- **Debug Agent**: Targeted bug fixing with learning integration

Each agent is designed with specific responsibilities, well-defined input/output contracts, and sophisticated interaction patterns that enable parallel execution while maintaining system coherence and reliability.
