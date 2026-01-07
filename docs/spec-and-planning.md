# Specification & Planning

Upfront planning freezes what will be built before any HDL is generated. Completing the L1–L5 checklist gives agents immutable constraints and lets the Orchestrator schedule work mechanically. This doc complements [agents.md](./agents.md#planning-phase-agents) and [architecture.md](./architecture.md).

## Workflow

1. **Specification Helper Agent + Human:** Iterative conversation to remove ambiguity, populate L1–L5, and record drafts in Task Memory.  
2. **Freeze:** Human signs off on the completed checklist; artifacts live under `artifacts/task_memory/specs/`.  
3. **Planner Agent:** Consumes the frozen checklist to emit the Design Context/DAG and frozen interfaces that drive execution.

## L1–L5 Checklist

### L1: Functional Intent

- **Purpose:** Establish the problem and success conditions in plain terms.  
- **Required fields:** role/behavior summary; key rules (ordering, losslessness, flag semantics, error behavior); performance intent; reset semantics; corner/illegal cases.  
- **Artifacts:** `artifacts/task_memory/specs/L1.json`, versioned with hash + author for replay.  
- **Gate:** All fields filled or marked “proposed by planner—pending approval.”

### L2: Interface Contract

- **Purpose:** Define I/O boundaries precisely to enable testbench generation and prevent interface drift.  
- **Required fields:** clock/reset (names, polarity, sync/async); I/O table (name, direction, width); handshake semantics; transaction unit; configuration parameters with defaults.  
- **Artifacts:** `artifacts/task_memory/specs/L2_interface.json`, aligned with `TaskMessage.context` and enums in `core/schemas/contracts.py`.  
- **Gate:** Interface frozen; changes require re-planning and propagation to dependents.

### L3: Verification Plan

- **Purpose:** Define how correctness will be verified before any code exists.  
- **Required fields:** test goals (happy-path, boundary, illegal); oracle strategy (scoreboard/reference model); stimulus strategy; pass/fail criteria; coverage intents (mapped to simulator metrics and Task Memory artifacts); reset/sequencing constraints.  
- **Artifacts:** `artifacts/task_memory/specs/L3_verification.json`, including coverage identifiers tracked as artifacts move through `Testing` → `Testing_Analysis` → `Passing`.  
- **Gate:** Every evaluation node has a verification strategy and traceable coverage counters.

### L4: Architecture / Microarchitecture

- **Purpose:** Choose plausible structure before coding to guide decomposition.  
- **Required fields:** block diagram (datapath, storage, FSMs); clocking & CDC plan; resource strategy (FIFO/RAM sizes tied to performance goals); latency/throughput budget mapped to L3 scenarios; assertions plan (SVA vs scoreboard).  
- **Artifacts:** `artifacts/task_memory/specs/L4_architecture.json`, mapping diagram elements to future DAG nodes with parent/child dependencies, interface references, and standard-library reuse tags.  
- **Gate:** Human approves structure (or explicitly defers for simple designs); this becomes the initial DAG topology for the Planner Agent.

### L5: Acceptance & Sign-off Plan

- **Purpose:** Define “done” before implementation starts.  
- **Required fields:** required artifacts (RTL, SVAs, testbenches, coverage reports, synthesis checks); threshold targets (test pass rate, coverage percentages, functional coverpoints); known exclusions/assumptions; synthesis target (FPGA/ASIC, tool).  
- **Artifacts:** `artifacts/task_memory/specs/L5_acceptance.json`, including machine-readable thresholds so Orchestrator workers know when to advance nodes.  
- **Gate:** Planner drafts defaults from L1–L4; human tightens/relaxes as needed. Acceptance metrics are the authoritative predicates for state transitions.

## Storage & Traceability

- All L-level artifacts live in Task Memory under `artifacts/task_memory/specs/` and retain hashes, authorship, and timestamps for deterministic replay.  
- The frozen Design Context references these artifacts by hash, and downstream tasks carry correlation IDs so execution steps can be tied back to the exact planning snapshot.  
- See [schemas.md](./schemas.md) for `TaskMessage`/`ResultMessage` fields used to transport this metadata.

## Planner Output Schema (execution handoff)

- **design_context.json**
  - `design_context_hash`: hash of `nodes`
  - `nodes` keyed by module id:
    - `rtl_file`, `testbench_file`: relative artifact paths to be written by agents
    - `interface.signals`: list of `{name, direction, width}`
    - `clocking`: `{clk: {freq_hz, reset, reset_active_low}}`
    - `coverage_goals`: `{branch, toggle}` (optional)
    - `uses_library`: list of standard-library components (optional)
  - `standard_library`: name→fingerprint map
- **dag.json**
  - `nodes`: list of DAG nodes with fields `id`, `type` (module), `deps` (list of ids), `state` (PENDING), `artifacts` (initially empty), `metrics` (initially empty)

Contracts:
- Paths in `design_context.json` are treated as immutable targets; the Orchestrator reads these, and agents/workers write artifacts to them.  
- Planner must validate interfaces against L2 and embed hashes/ids so execution tasks carry consistent correlation IDs.  
- If the format evolves, bump a version field and keep backward compatibility in the Orchestrator until all tasks are migrated.
