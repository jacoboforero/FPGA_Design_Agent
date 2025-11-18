# Multi-Agent Hardware Design System: Agent Architecture

Agents are logical roles that run inside the agent-worker runtime. They receive tasks from the Orchestrator via the broker and operate with a frozen Design Context. System context lives in [architecture.md](./architecture.md); queue mechanics live in [queues-and-workers.md](./queues-and-workers.md).

## Planning Phase Agents

### Specification Helper Agent

**Role:** Human-AI collaboration interface for specification convergence.  
**Responsibilities:** Guide designers through the L1–L5 checklist, ask clarifying questions, propose edits on request, and validate completeness.  
**Inputs:** Human drafts and responses.  
**Outputs:** Frozen L1–L5 artifacts plus change history stored in Task Memory.

### Planner Agent

**Role:** Automated strategic decomposer.  
**Responsibilities:** Translate the frozen specification into a Directed Acyclic Graph (DAG), define module boundaries, propagate interfaces, and identify reusable components.  
**Inputs:** Frozen L1–L5 artifacts; standard component library definitions.  
**Outputs:** Frozen Design Context (DAG + interfaces) that seeds execution.

## Execution Phase Agents

### Implementation Agent

**Role:** RTL generation.  
**Responsibilities:** Convert declarative specs into synthesizable HDL, implement state machines/datapaths/storage, and strictly honor frozen interfaces.  
**Outputs:** Self-contained HDL for a single module plus implementation notes.

### Testbench Agent

**Role:** Verification environment generation.  
**Responsibilities:** Build stimulus, oracles, and coverage aligned to the L3 verification plan; ensure compatibility with module interfaces.  
**Outputs:** SystemVerilog testbench and coverage constructs.

### Reflection Agent

**Role:** AI-powered failure analysis.  
**Responsibilities:** Analyze distilled waveforms/logs, generate root-cause hypotheses and investigation paths, and produce structured insights for debugging.  
**Outputs:** Reflection insights stored in Task Memory for downstream use.

### Debug Agent

**Role:** Targeted bug fixing.  
**Responsibilities:** Combine failing HDL/testbench context with reflection outputs, hypothesize root causes, and propose precise code changes without breaking interfaces.  
**Outputs:** Updated HDL/testbench artifacts and debugging rationale.

## Interaction Patterns

- Tasks flow one-way through the broker from Orchestrator to agent-worker runtime; agents do not call each other directly.  
- Agents read from the frozen Design Context and write artifacts, logs, and insights to Task Memory.  
- Iterative refinement is supported: failed tests can trigger distill → reflect → debug loops before re-running tests.  
- See [queues-and-workers.md](./queues-and-workers.md) for queue bindings and DLQ handling.

## Agent State Management

- **Implementation State:** Tracks per-task progress and intermediate attempts within Task Memory.  
- **Validation State:** Records checklist completion for planning agents and interface/test conformance for execution agents.  
- **Learning State:** Optional per-agent memory of past analyses to avoid repeating failed strategies.

## Error Handling & Escalation

- Agents validate task payloads against shared schemas before acting; unrecoverable payload issues should be rejected to the DLQ.  
- When stuck (e.g., repeated failures with no progress), agents surface context and hypotheses in Task Memory to assist human escalation triggered by the Orchestrator.  
- Poison-pill handling and DLQ monitoring are described in [queues-and-workers.md](./queues-and-workers.md); message constraints are in [schemas.md](./schemas.md).
