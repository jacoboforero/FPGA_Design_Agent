# Vision and User Experience

This project exists to compress the path from idea to working FPGA design.

The goal is not just "generate RTL." The goal is to help teams ship faster by turning fuzzy requirements into testable hardware artifacts with less manual overhead, less context switching, and faster iteration loops.

## Product Vision
- Accelerate time-to-market for FPGA designs.
- Use an LLM-based multi-agent system to automate RTL generation and verification workflow steps.
- Keep humans in control at high-leverage decision points while automating repetitive engineering execution.

## Two Core User Groups
This platform serves two different users with two different outcomes.

1. Hardware Engineers
- Goal: get from design intent to usable RTL faster.
- Primary interface: guided, conversational CLI flow.
- Success looks like: faster iteration, cleaner spec handoff, and quicker path to implementation/testing artifacts.

2. Researchers
- Goal: evaluate model/system behavior rigorously and reproducibly.
- Primary interface: scriptable benchmark workflow.
- Success looks like: comparable results across models/settings with official-style scoring artifacts.

## What The Experience Should Feel Like
You should be able to open a terminal, describe what you need, and feel like the system is collaborating with you instead of asking you to learn a framework.

The intended experience is:
1. Start with a simple CLI flow.
2. Refine your spec with a spec-helper chatbot.
3. Approve the plan.
4. Hand off to agentic execution.
5. Review generated outputs and iterate.

In parallel, the same platform should let you run scripted benchmark campaigns to compare models and settings in a reproducible way.

## Two User Paths
- **Engineer path** (`cli.py` full flow): refine spec with a spec helper chatbot, approve plan, run agentic execution, inspect outputs, iterate.
- **Research path** (`cli.py benchmark`): run controlled benchmark campaigns, compare presets/models, and analyze official benchmark summaries.

These paths share core infrastructure, but they are intentionally optimized for different users.

## Current UX
The experience is designed to feel like guided acceleration, not tool orchestration.

- **Clear flow, low friction**: you move through a straightforward sequence of spec, plan, and execution.
- **Confidence before automation**: there is an explicit handoff point where you approve execution after planning.
- **Helpful spec refinement**: the spec helper can work the way you prefer:
  - edit directly in your editor,
  - answer in conversational chat,
  - or accept drafted suggestions.
- **Constructive guidance**: when key details are missing, the system points out what is missing and why it matters.
- **Interactive when you want it, scriptable when you need it**: teams can run hands-on sessions or automate runs via CLI flags and config.
- **Readable run experience**: execution can be shown as narrative output or raw progress, depending on preference.
- **Benchmark-ready workflow**: model comparisons are first-class, with scriptable benchmark runs and repeatable settings.
- **Preflight mindset**: a doctor/check workflow helps catch setup issues before expensive runs.

## Why This Matters To Teams
- Faster spec-to-implementation cycles.
- Better consistency in how requirements are translated into artifacts.
- Clearer handoff between product intent and verification intent.
- A path to evaluate LLM/model strategy with real benchmark evidence, not intuition.

## In One Sentence
This is a CLI-first FPGA acceleration system: conversational where it should be, autonomous where it can be, and benchmarkable end-to-end when you need hard evidence.
