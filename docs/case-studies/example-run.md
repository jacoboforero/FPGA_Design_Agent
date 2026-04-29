# Case Study: Counter Spec To Verified RTL

This case study uses the `counter3` demo fixture in
`tests/test_specs/01_counter3_basic.txt`. It is representative of the intended
engineer workflow: take a hardware spec, freeze planning intent, generate RTL
and verification collateral, then validate through deterministic EDA stages.

A compact checked-in artifact snapshot for this case study lives under
[`../../examples/counter3`](../../examples/counter3). Fresh local runs still
write full outputs under `artifacts/`.

## Problem

Build a 3-bit synchronous up counter with enable and a one-cycle rollover pulse.
The design has:

- active-low asynchronous reset
- one count update per rising clock edge when enabled
- hold behavior when disabled
- wrap from `7` to `0`
- rollover asserted only on the wrap cycle

## Input Specification

The input fixture is already organized around the planning levels the system
expects:

- L1 functional intent: counter behavior, reset semantics, corner cases
- L2 interface contract: `clk`, `rst_n`, `en`, `count[2:0]`, `rollover`
- L3 verification plan: reset, hold, increment, and wrap scenarios
- L4 architecture plan: 3-bit register, adder, wrap comparator
- L5 acceptance contract: required RTL, testbench, lint, simulation, and
  coverage artifacts

## Planning Contract

The spec helper and planner turn the frozen L1-L5 content into:

- `artifacts/generated/design_context.json`
- `artifacts/generated/dag.json`

For this single-module example, the DAG contains one implementation node:
`counter3`.

## Generated Artifacts

A successful run writes representative artifacts under:

- `artifacts/generated/rtl/counter3.sv`
- `artifacts/generated/rtl/counter3_tb.sv`
- `artifacts/task_memory/counter3/`
- `artifacts/observability/`

The exact run directory depends on the run name and timestamp.

## Verification Flow

The orchestrator schedules the stage sequence:

1. implementation agent generates RTL
2. lint worker checks RTL
3. testbench agent generates a self-checking testbench
4. testbench lint worker validates the testbench
5. simulation worker compiles and runs with Icarus Verilog/VVP
6. acceptance worker checks required artifacts and pass/fail evidence

If simulation fails, the repair path is:

1. distillation worker extracts compact failure evidence from logs/waveforms
2. reflection agent generates hypotheses and debug focus
3. debug agent patches RTL or testbench code
4. orchestrator reruns the appropriate validation stages with bounded retries

## Reproduce Locally

Preferred container path:

```bash
make build
make up
make deps
make shell
PYTHONPATH=. poetry run python3 apps/cli/cli.py \
  --config config/runtime.yaml \
  --spec-file tests/test_specs/01_counter3_basic.txt \
  --run-name counter3_case_study \
  --yes
```

Host fallback:

```bash
poetry install --with dev
PYTHONPATH=. poetry run python3 apps/cli/cli.py \
  --config config/runtime.yaml \
  --spec-file tests/test_specs/01_counter3_basic.txt \
  --run-name counter3_case_study \
  --yes
```

## Why This Matters

The important output is not only the Verilog file. The system also preserves the
planning contract, DAG, testbench, logs, task memory, and observability data.
That makes the result inspectable and debuggable, which is the main difference
between this workflow and a single prompt that emits RTL once.
