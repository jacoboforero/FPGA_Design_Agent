# Agents

All LLM-backed roles run through the shared agent worker runtime and exchange messages through the orchestrator/broker flow.

## Planning Agents
- **Specification Helper**
  - Guides L1-L5 completion and clarifies missing fields.
  - Supports interactive answers, editor edits, and draft proposals.
- **Planner**
  - Reads frozen specs and lock metadata.
  - Emits `design_context.json` and `dag.json` for execution.

## Execution Agents
- **Implementation**
  - Generates RTL for a node using interface + module contract context.
  - Enforces integration wiring constraints when child modules are present.
- **Testbench**
  - Generates TB code for planned verification behavior.
- **Reflection**
  - Uses distilled failure artifacts to produce structured hypotheses and probes.
- **Debug**
  - Applies patch proposals to RTL/TB and validates patch quality expectations.

## Important Clarification
- `IntegrationAgent` exists as an enum value for compatibility, but there is no standalone integration worker runtime today.
- Integration behavior is handled by implementation/debug context and module contracts.

## Operational Behavior
- Agents return `ResultMessage` with explicit success/failure status.
- Payload/schema validation failures should fail fast and route by queue policy.
- Retry policy is orchestrator-controlled, not agent self-looping.

## Related Code
- `agents/spec_helper/worker.py`
- `agents/planner/worker.py`
- `agents/implementation/worker.py`
- `agents/testbench/worker.py`
- `agents/reflection/worker.py`
- `agents/debug/worker.py`
- `core/schemas/contracts.py`
