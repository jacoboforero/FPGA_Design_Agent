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

## Agent I/O Contracts (practical defaults)

Keep context useful but bounded. All agents share:
- `context.node_id`, `context.interface.signals` (name/direction/width)
- `context.coverage_goals` (optional), `context.rtl_path`, `context.testbench_path`
- `context.design_context_path`, `context.dag_path` (optional)
- `context.prior_artifacts` (stage→path/log), `context.settings` (optional model/temperature/max_tokens)

Per agent:

- **Implementation**
  - Inputs: shared + `spec_summary` (short intent), `demo_behavior` (optional stub)
  - Outputs: RTL to `rtl_path`; log summarizing generation (model, assumptions)
  - Success: file exists, non-empty, ports match interface
  - Retry/timeout: 1 retry on transient LLM error; timeout ~60–120s
  - DLQ: schema/interface mismatch or repeated failures

- **Testbench**
  - Inputs: shared + `test_plan` (scenarios/goals), `coverage_goals`
  - Outputs: TB to `testbench_path`; log listing scenarios/coverage checks
  - Success: TB references module/ports; failure if missing ports or empty
  - Retry/timeout: 1 retry; timeout ~60–120s
  - DLQ: schema/interface issues, repeated failure

- **Reflection**
  - Inputs: shared + `distilled_dataset` path/summary, `sim_log` path/snippet
  - Outputs: insights (hypotheses, failure points, probes) in log or JSON artifact
  - Success: non-empty insights; failure on missing inputs/empty output
  - Retry/timeout: 1 retry; timeout ~60s
  - DLQ: missing required inputs or repeated empty output

- **Debug**
  - Inputs: shared + `failure_signature`, `reflection_insights`, `latest_rtl_path`/`testbench_path`
  - Outputs: updated RTL/TB if changed; log with root-cause hypothesis and change summary
  - Success: writes changes or justified no-op; failure on interface conflict/empty result
  - Retry/timeout: 1 retry; timeout ~90–120s
  - DLQ: interface mismatch, schema error, repeated empty/no-op without rationale

- **Specification Helper**
  - Inputs: shared + `questions` (list), `current_spec` (short text), `checklist_state` (L1–L5 flags)
  - Outputs: updated spec text/checklist; log summarizing clarifications
  - Success: returns updated text/state; failure on empty/invalid output
  - Retry/timeout: 1 retry; timeout ~60s
  - DLQ: malformed checklist/spec or repeated empty responses

LLM usage: unless overridden in `context.settings`, use the default gateway model with conservative temperature and token limits; log model name and key assumptions.
