# AI-for-EDA Project Brief: FPGA Design Agent

FPGA Design Agent is a planning-first agentic AI prototype for RTL and FPGA
design automation. It turns hardware specifications into structured planning
contracts, generated Verilog RTL, verification artifacts, repair traces, and
benchmark results.

## Why It Exists

Prompt-to-Verilog is not enough for practical hardware work. Real RTL workflows
depend on clarified requirements, interface contracts, verification intent,
debug evidence, and repeatable tool checks. This project explores an agentic
workflow where planning and verification are first-class parts of generation.

## Architecture Summary

- The CLI collects or loads a hardware spec, runs planning, shows the generated
  DAG, and then starts execution.
- The planner emits `design_context.json` and `dag.json`.
- The orchestrator dispatches work through RabbitMQ, tracks node state, gates
  dependencies, and handles retries.
- LLM agents handle specification help, planning, RTL implementation, testbench
  generation, reflection, debug, and finalization.
- Deterministic workers handle RTL linting, testbench linting, simulation,
  acceptance checks, and failure distillation.
- Runs write generated RTL, task memory, observability logs, metrics, and
  benchmark reports under `artifacts/`.

## What It Demonstrates

- Agent/workflow orchestration for technical engineering domains.
- Structured output contracts and prompt engineering around RTL generation.
- Integration with local EDA tools such as Verilator and Icarus Verilog.
- Failure-repair loops that distill logs, reflect on failure evidence, patch
  code, and rerun validation.
- VerilogEval v2-backed benchmark execution and comparison.
- Product-facing CLI and documentation for an inspectable local workflow.

## Tech Stack

Python, Pydantic, RabbitMQ, Docker, Verilog/SystemVerilog, Verilator, Icarus
Verilog, OpenAI-compatible LLM providers, RAG components, pytest, and local
artifact/observability stores.

## Five-Minute Review Path

1. Read the README section
   [Relevance to AI-for-EDA / Chip Design Tools](../README.md#relevance-to-ai-for-eda--chip-design-tools).
2. Review [architecture.md](architecture.md) for planning, orchestration, and
   state-machine context.
3. Review [queues-and-workers.md](queues-and-workers.md) for the agent/worker
   split and broker routing.
4. Review [workflows/failure-repair-loop.md](workflows/failure-repair-loop.md)
   for the debug loop.
5. Review [../examples/counter3](../examples/counter3) for compact checked-in
   spec, planning, RTL, and testbench artifacts.
6. Review [case-studies/example-run.md](case-studies/example-run.md) for a
   concrete spec-to-RTL walkthrough.
7. Review [../PERSONAL_CONTRIBUTIONS.md](../PERSONAL_CONTRIBUTIONS.md) for
   individual ownership.

## Fit For Chip-Design AI Tooling Roles

The project is most relevant to roles that combine full-stack/product
engineering with agentic AI workflows for EDA, RTL, simulation, verification,
and developer tooling. It is not presented as proof of senior RTL or UVM
expertise; it is proof of hands-on software ownership in the product category
of agentic AI tools for chip-design workflows.
