# Planning-First Hardware Design Automation

This repository contains a hardware design automation system built around a
simple premise: the hardest part of going from a human specification to working
RTL is not just code generation. It is clarifying design intent early enough
that implementation and verification do not break down later.

The project is therefore intentionally planning-first. It helps a hardware
engineer refine a specification, freezes that intent into a structured planning
contract, and only then runs RTL generation and verification through an
orchestrated pipeline of reasoning agents, deterministic workers, and standard
EDA tools.

The primary output is verified Verilog RTL, along with the execution evidence
needed to understand how it was produced and why a run passed or failed.

## Relevance to AI-for-EDA / Chip Design Tools

This project is an agentic AI prototype for RTL and FPGA design automation.

It demonstrates:

- planning-first hardware spec refinement before RTL generation
- LLM agents for specification help, implementation, testbench generation,
  reflection, and debug
- deterministic EDA workers for linting, simulation, acceptance checks, and
  failure distillation
- RabbitMQ-backed orchestration with dependency gating, retries, and run-scoped
  result routing
- local tool integration with Verilator and Icarus Verilog
- observability artifacts, task memory, token/cost tracking, and execution
  traces
- VerilogEval v2-backed benchmarking for reproducible AI/EDA experiments

The goal is not one-shot prompt-to-Verilog generation. The goal is an
inspectable human-in-the-loop workflow that helps hardware engineers clarify
specs, generate RTL, verify behavior, debug failures, and preserve execution
evidence.

## Five-Minute Technical Review

If you are reviewing the repo for fit rather than running the whole stack, start
here:

1. [docs/hiring-brief.md](docs/hiring-brief.md) for the one-page technical
   summary.
2. [examples/counter3](examples/counter3) for a compact spec, planning
   contract, DAG, RTL, and testbench artifact pack.
3. [docs/architecture.md](docs/architecture.md) for the planning/orchestration
   model.
4. [docs/workflows/failure-repair-loop.md](docs/workflows/failure-repair-loop.md)
   for the lint/sim/debug retry path.
5. [docs/benchmark-methodology.md](docs/benchmark-methodology.md) for the
   VerilogEval v2 benchmarking policy.

## Why This Project Exists

Manual translation of FPGA and digital hardware specifications into RTL is slow,
fragile, and verification-heavy. In real hardware workflows, a large share of
the schedule is spent not on typing code, but on:

- resolving ambiguities in the specification
- preserving interface and timing intent
- building and fixing verification collateral
- debugging failures across code, testbenches, and tools

This project was built as an attempt to narrow that design gap without
pretending the engineer should disappear from the loop. The goal is to augment
hardware design work, not replace it with a one-shot prompt-to-Verilog wrapper.

## What The System Does

At a high level, a normal run looks like this:

1. A draft hardware specification is provided interactively or from file.
2. A specification helper resolves missing details and freezes the design into a
   structured planning artifact.
3. A planner turns that frozen intent into an execution-ready design context and
   dependency graph.
4. An orchestrator dispatches implementation and verification work across agents
   and deterministic workers.
5. If a stage fails, the system can distill the failure, reflect on it, patch
   code, and retry.
6. The run emits generated RTL, verification artifacts, and observability logs.

The same codebase also supports a second use case: reproducible benchmarking for
AI/EDA research. In that mode, the repository acts as a harness for running
VerilogEval v2 experiments and comparing models or system settings under a
consistent workflow.

## Design Philosophy

Two ideas drive the structure of the repo:

- Specification quality matters as much as generation quality. If the spec is
  ambiguous, downstream automation becomes brittle.
- Verification is a first-class AI problem. It should not be treated as an
  afterthought after RTL emission.

That leads to a system that is deliberately different from a single chat prompt
that emits RTL once and hopes for the best.

## High-Level Technical Context

If you are reading this repository for architecture or research reasons, these
are the most important framing ideas:

- Planning comes before execution.
  The repo uses a structured planning contract organized around functional
  behavior, interface, verification intent, architecture, and acceptance
  criteria. Generation is downstream of that planning step.

- Agents and workers are intentionally different.
  Agents handle LLM-assisted reasoning tasks such as spec clarification,
  implementation, reflection, and debug. Workers handle deterministic tasks such
  as linting, simulation, acceptance checks, and failure distillation.

- The orchestrator is part of the core design, not just glue code.
  Execution is DAG-driven, queue-backed, and state-machine controlled. That is
  how retries, dependency gating, and run-scoped isolation are enforced.

- The toolchain is local and inspectable.
  The system runs on the user's machine, uses Docker for reproducible setup,
  RabbitMQ for task routing, and standard EDA tools such as Verilator and
  Icarus Verilog for checking generated designs.

- Memory and observability are built in.
  Engineer runs can use archived design summaries and retrieval. Runs also emit
  task memory, metrics, token/cost tracking, and execution traces so the system
  can be inspected instead of treated as a black box.

- The repository serves both engineering and research.
  There is an interactive CLI path for design work and a benchmark path for
  controlled evaluation. Understanding that split makes the repo much easier to
  navigate.

## What This Repository Is Not

- It is not just a benchmark harness.
- It is not just a chatbot around an RTL prompt.
- It is not a monolithic agent that hides all intermediate structure.
- It is not a hosted service; the system is designed to run locally with local
  configuration, local artifacts, and local tool integration.

## Benchmarking

The benchmark side of the repository is built around the VerilogEval v2
submodule at `third_party/verilog-eval` (currently pinned at `v2.0.0`). The
harness can run canonical full-set campaigns, bind benchmark-provided oracle
assets, and delegate final scoring to official analyzer outputs.

That benchmark family matters because public AI-for-EDA systems report against
VerilogEval-v2. This repo uses it as a reproducible evaluation harness for the
agent pipeline, not as a claim that any local run is directly comparable without
matching model, prompt, toolchain, and runtime policy.

### Current Benchmark Snapshot

These are local full-set canonical VerilogEval-v2 snapshots scored by the
official analyzer (`n=1`). They are meant to show system progress at a glance,
not to claim a controlled model leaderboard.

| Model / run | System state | Pass rate | Tests passed | Cost |
| --- | --- | ---: | ---: | ---: |
| GPT-4.1, optimized repair loop | Current full run | 87.82% | 137/156 | $8.26 |
| GPT-4.1 | Earlier full-set snapshot | 82.05% | 128/156 | $3.73 |
| GPT-4o | Earlier full-set baseline | 75.00% | 117/156 | $6.03 |
| GPT-4.1 mini | Earlier full-set snapshot | 73.72% | 115/156 | $4.47 |

The latest GPT-4.1 run is +9 solved cases over the earlier GPT-4.1 full-set
snapshot and +20 over the GPT-4o full-set baseline. In paper context, this is
above the single-shot/model-only GPT-4o and GPT-4.1 reference numbers we found,
but still below top reported agentic systems such as ChipAgents and MAGE. See
[`docs/benchmark-optimization-log-20260429.md`](docs/benchmark-optimization-log-20260429.md)
for run artifacts, caveats, and paper links.

Generated benchmark and interactive run outputs live under `artifacts/` and are
ignored by git. Shareable, compact examples belong under `examples/`; see
[`examples/counter3`](examples/counter3) for a curated artifact pack.

## Quick Start

Containerized setup is the preferred path because it keeps the toolchain and
broker environment reproducible.

Prerequisites:

- Docker and Docker Compose
- Git submodules initialized
- Optional model credentials in your shell or `.env`

From the repository root:

```bash
git submodule update --init --recursive
make build
make up
make deps
make cli
```

If you want a shell inside the normalized container environment:

```bash
make shell
```

Host fallback:

```bash
poetry install --with dev
PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml
```

Generated outputs are written under:

- `artifacts/generated/`
- `artifacts/task_memory/`
- `artifacts/observability/`

The repository keeps those outputs local. Commit small curated examples under
`examples/` instead of committing generated run trees.

## Recommended Reading Order

If you want to understand the project rather than immediately run it, this is
the reading order I recommend:

1. [docs/overview.md](docs/overview.md)
   This gives the shortest accurate explanation of what happens in a run.
2. [docs/spec-and-planning.md](docs/spec-and-planning.md)
   Read this next if you want to understand why the repo is planning-first.
3. [docs/architecture.md](docs/architecture.md)
   This describes the runtime split between planning, execution, queues, and the
   state machine.
4. [docs/agents.md](docs/agents.md)
   This explains which tasks are LLM-mediated and why.
5. [docs/queues-and-workers.md](docs/queues-and-workers.md)
   Read this to understand deterministic stages and RabbitMQ routing.
6. [docs/observability.md](docs/observability.md)
   Important if you care about traces, token usage, or failure inspection.
7. Choose a workflow path:
   [docs/workflows/interactive-run.md](docs/workflows/interactive-run.md) for
   the engineer-facing CLI flow, or
   [docs/workflows/benchmark-run.md](docs/workflows/benchmark-run.md) for the
   research benchmark flow.
8. [docs/benchmark-methodology.md](docs/benchmark-methodology.md)
   Read this before interpreting benchmark numbers or comparing runs.

If you want the full docs map after that, start at
[docs/README.md](docs/README.md).

## Repo Map

- `apps/cli/`: entrypoints for engineer runs, doctor checks, and benchmark runs
- `agents/`: LLM-backed reasoning roles
- `workers/`: deterministic lint, simulation, acceptance, and distillation
  stages
- `orchestrator/`: DAG execution, retries, and state transitions
- `adapters/`: LLM, RAG, and observability integrations
- `core/`: shared schemas, runtime config, prompting, and broker utilities
- `config/`: runtime manifests and domain configuration
- `docs/`: architecture notes, runbooks, and methodology
- `examples/`: small curated review artifacts that replace generated run dumps
- `packaging/homebrew/`: experimental Homebrew/demo packaging
- `apps/vscode-extension/` and `apps/ui_backend/`: experimental editor/UI
  surfaces
- `tests/`: unit and workflow-level validation

## Status And License

This is a research/capstone prototype, not a hosted production service. The core
CLI, agent orchestration, EDA-worker pipeline, benchmark flow, and docs are the
main review surface. The Homebrew packaging, VS Code extension, and UI backend
are experimental surfaces.

This repository is currently published as all rights reserved. See
[LICENSE](LICENSE).

## Common Entry Points

Engineer flow:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml
```

Environment preflight:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.yaml
```

Benchmark problem discovery:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark list-problems --config config/runtime.benchmark.yaml --max-problems 10
```

Benchmark dry run:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign smoke --max-problems 3 --dry-run
```

## Documentation And Validation

Useful top-level docs:

- [docs/README.md](docs/README.md)
- [docs/overview.md](docs/overview.md)
- [docs/spec-and-planning.md](docs/spec-and-planning.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/workflows/interactive-run.md](docs/workflows/interactive-run.md)
- [docs/workflows/benchmark-run.md](docs/workflows/benchmark-run.md)

Useful validation commands:

```bash
python3 scripts/validate_docs.py
pytest tests/apps -q
pytest tests/orchestrator -q
pytest tests/workers -q
pytest tests/agents -q
```
