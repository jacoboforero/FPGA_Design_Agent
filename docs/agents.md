# Agents

## Purpose
Define each LLM-backed agent's responsibility and expected I/O behavior.

## Audience
Engineers implementing or reviewing agent prompts, contracts, and completion criteria.

## Scope
Role-level expectations and artifact contracts. Queue and state mechanics are documented elsewhere.

## Planning Agents
- **Specification Helper**: converges and locks L1-L5 artifacts.
- **Planner**: reads locked specs and emits design context + DAG.

## Execution Agents
- **Implementation**: writes RTL to target path while preserving interface contract.
- **Testbench**: writes TB source for planned verification goals.
- **Reflection**: produces structured hypotheses from distilled failure evidence.
- **Debug**: patches RTL/TB and records rationale.

## Operational Rules
- Agents publish `ResultMessage` with explicit success/failure status.
- Schema mismatch or non-recoverable payload errors should fail fast and route to DLQ policy.
- Retries are controlled by orchestrator policy, not agent-local loops.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/agents/`
- `/home/jacobo/school/FPGA_Design_Agent/core/schemas/contracts.py`

## Related Docs
- [schemas.md](./schemas.md)
- [spec-and-planning.md](./spec-and-planning.md)
- [components/llm-gateway.md](./components/llm-gateway.md)
