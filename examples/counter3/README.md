# Counter3 Curated Example

This directory is a small checked-in artifact pack for technical reviewers. It
shows the shape of a spec-to-RTL run without committing large generated output
trees under `artifacts/`.

## Files

- `spec/counter3_basic.txt`: the source hardware specification.
- `planning/design_context.json`: representative planning contract emitted by
  the planning stage.
- `planning/dag.json`: single-node execution DAG for the counter module.
- `rtl/counter3.sv`: generated RTL for the counter.
- `rtl/counter3_tb.sv`: generated self-checking testbench.

## Design

The example implements a 3-bit synchronous up counter with enable, active-low
asynchronous reset, hold behavior when disabled, wrap from `7` to `0`, and a
one-cycle `rollover` pulse on the wrap cycle.

## Why This Exists

Full benchmark and interactive runs create large local outputs under
`artifacts/`. Those outputs are intentionally ignored by git. This example gives
reviewers a compact, stable snapshot of the artifact structure while keeping
the repository readable.
