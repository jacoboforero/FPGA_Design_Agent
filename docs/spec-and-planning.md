# Specification & planning

Freeze what will be built before any HDL is generated. L1–L5 lives under `artifacts/task_memory/specs/` and feeds the planner.

## Workflow
1) Spec helper + human iterate on L1–L5.  
2) Human locks specs (`lock.json` written under `artifacts/task_memory/specs/`).  
3) Planner consumes the locked specs and writes `design_context.json` + `dag.json` under `artifacts/generated/`.

## L1–L5 (keep it lean)
- **L1 Functional intent:** plain-language behavior, reset rules, key edge cases.
- **L2 Interface:** clock/reset, I/O table (name/direction/width), handshake semantics, params/defaults.
- **L3 Verification:** test goals, oracle/scoreboard plan, stimulus strategy, pass/fail criteria, coverage intents.
- **L4 Architecture:** simple block/FSM sketch, clocking/CDC notes, resource choices, latency/throughput goals.
- **L5 Acceptance:** what “done” means (artifacts required, coverage/threshold targets, exclusions/assumptions).

## Planner outputs (execution handoff)
- `design_context.json`
  - `nodes` keyed by module: `rtl_file`, `testbench_file`, `interface.signals`, `clocking`, `coverage_goals`, `uses_library` (optional)
  - `design_context_hash`, `standard_library`
- `dag.json`
  - `nodes`: `{id, type, deps, state=PENDING, artifacts={}, metrics={}}`

Contracts:
- Paths in the design context are targets; orchestrator reads them, agents/workers write to them.
- Interface in L2 must match what the planner emits; changes require re-planning.

## Multi-module DAGs
To generate multi-node DAGs, include `block_diagram` nodes and `dependencies` in `L4_architecture.json`.
For each module referenced in the block diagram, provide per-module specs named:
`L1_functional_<module>.json`, `L2_interface_<module>.json`, `L3_verification_<module>.json`, `L5_acceptance_<module>.json`.
The planner fails if any referenced module spec is missing.
