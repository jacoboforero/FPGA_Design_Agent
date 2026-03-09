# Specification and Planning

Planning is a hard gate before execution. The goal is to freeze what should be built and how it should be verified before any RTL generation starts.

## Planning Workflow
1. Collect spec text (interactive editor or provided file).
2. Complete missing L1-L5 fields.
3. Persist frozen artifacts and `lock.json` under `artifacts/task_memory/specs/`.
4. Run planner to emit `artifacts/generated/design_context.json` and `artifacts/generated/dag.json`.

## L1-L5 Layers
- **L1**: functional intent and corner-case behavior.
- **L2**: interface contract (signals, widths, clock/reset, handshake semantics).
- **L3**: verification plan (goals, scenarios, oracle strategy, coverage intent).
- **L4**: architecture/dependencies/connections.
- **L5**: acceptance artifacts and measurable thresholds.

## Interactive Spec UX
When fields are missing, the spec helper loop lets you:
1. Edit the spec in your editor.
2. Answer in chat.
3. Ask the helper to propose drafts.

This continues until required fields are complete or explicitly handled.

## Multi-Module Behavior
- Use repeated `Module: <name>` sections in spec text.
- Optional `Top: <module>` sets top module.
- Planner validates child specs and connection coverage for declared dependencies.

## Frozen Artifacts Written
- `L1_functional*.json`
- `L2_interface*.json`
- `L3_verification*.json`
- `L4_architecture*.json`
- `L5_acceptance*.json`
- `frozen_spec*.json`
- `lock.json`

## Related Code
- `apps/cli/spec_flow.py`
- `orchestrator/planner.py`
- `orchestrator/preplan_validator.py`
- `core/schemas/specifications.py`
