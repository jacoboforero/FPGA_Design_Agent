# Two-Minute Demo Script

## Goal

Show that FPGA Design Agent is an agentic RTL/EDA workflow system, not a
one-shot Verilog chatbot.

## Script

0:00 - Open with the project.

> I built FPGA Design Agent, a planning-first agentic AI system for RTL and FPGA
> design automation. It takes a hardware spec, helps refine it into a structured
> planning contract, and then drives LLM reasoning stages plus deterministic EDA
> workers toward verified functional Verilog. I designed and implemented the
> core workflow while also coordinating execution for the capstone team.

0:15 - Explain the thesis.

> The key idea is that prompt-to-Verilog is not enough. Hardware automation
> breaks down when specs are ambiguous, interfaces are underspecified, or
> verification is treated as an afterthought. This system clarifies intent first
> and freezes it into structured planning artifacts before generation.

0:35 - Show the README and architecture docs.

> The pipeline separates LLM reasoning stages from deterministic EDA workers.
> Agents handle spec help, implementation, testbenching, reflection, and debug.
> Workers handle lint, simulation, acceptance, and failure distillation.

0:55 - Show the CLI.

> The CLI is the product surface. It collects specs, runs planning, shows the
> generated DAG, asks for execution confirmation, and then starts the
> orchestrated run.

1:15 - Show generated artifacts.

> A run writes the generated RTL, testbench, logs, task memory, and observability
> artifacts locally so the engineer can inspect what happened instead of
> trusting a black-box model response.

1:35 - Show failure-repair or benchmark artifacts.

> When simulation fails, the system can distill the failure log and waveform
> context, ask a reflection agent for hypotheses, run a debug agent to patch RTL
> or testbench code, and retry bounded validation. The same platform also runs
> VerilogEval v2-backed benchmarks for repeatable AI/EDA experiments.

1:55 - Close with role fit.

> This is why ChipAgents is the role I am targeting. My strength is building
> full-stack agentic workflow software for technical engineering domains, and
> this project is directly in the category of agentic AI tooling for RTL,
> simulation, and verification workflows.

## Supporting Shots

- README top section and benchmark framing.
- `examples/counter3/` curated spec, planning, RTL, and testbench files.
- `docs/architecture.md` state machine.
- `apps/cli/cli.py` command surface.
- `orchestrator/orchestrator_service.py` repair loop.
- `workers/sim/worker.py` and `workers/distill/worker.py`.
- Current local `artifacts/generated/rtl/` and `artifacts/benchmarks/verilog_eval/`
  outputs if a fresh run has been produced.
