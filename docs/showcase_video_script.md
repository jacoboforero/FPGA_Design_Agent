# Senior Design Showcase Video Plan

## Core Message

Use this as the one-sentence thesis:

> We built a multi-agent hardware design platform that does not stop at code generation. It plans, decomposes, configures different models, retrieves prior design knowledge, invokes real EDA tools, benchmarks itself, and records cost and execution evidence.

## Target Runtime

Target final runtime: `8:30` to `9:15`

That is safely inside the required range without risking an accidental 11+ minute cut.

## Best Structure For This Audience

1. `0:00-0:25` hook
2. `0:25-1:05` Jacobo intro and problem framing
3. `1:05-2:20` first team pass: remaining members, what they built and why it matters
4. `2:20-3:05` architecture and system novelty
5. `3:05-4:05` strongest evidence and results
6. `4:05-5:50` second team pass: one proof artifact per member
7. `5:50-6:25` industry value
8. `6:25-7:05` research value
9. `7:05-8:20` broader impact and close
10. `8:20-9:00` final close

This structure keeps all 6 members on screen twice while spending most of the time on novelty and significance, not command typing.

## Time-Coded Script

### 0:00-0:25 - Hook

Speaker: Jacobo voiceover or on camera

Visuals:

- fast montage of:
  - terminal
  - DAG
  - benchmark result
  - cost summary
  - tool registry
  - all 6 team members
- title card:
  - `MHD: Multi-Agent Hardware Design System`
  - `Senior Design Showcase`

Script:

> Most AI-for-hardware-design demos stop at code generation.  
> Ours goes further.  
> It plans work, decomposes multi-module designs, supports different model backends, retrieves prior design knowledge, invokes EDA tools, benchmarks itself, and records cost and execution evidence.

### 0:25-1:05 - Jacobo Intro And Why This Matters

Speaker: Jacobo

Visuals:

- Jacobo on camera
- lower third: `Jacobo Forero | Agent Orchestration and Interfaces`
- slide with two columns:
  - `Industry: faster path from spec to verified artifact`
  - `Research: controlled evaluation of agentic hardware-design workflows`

Script:

> Hi, I'm Jacobo Forero, and I led agent orchestration and user-facing interfaces for the project.  
> Hardware design workflows are still full of manual translation, tool friction, and repeated iteration between intent, implementation, and verification.  
> We wanted to reduce that friction with a planning-first multi-agent system for hardware design.  
> For industry, the value is shorter iteration loops and better traceability.  
> For research, the value is a hardware-design workflow that can be evaluated with benchmark evidence instead of intuition alone.

### 1:05-1:20 - Dexter First Appearance

Visuals:

- Dexter on camera
- lower third: `Dexter Pressley | LLM Interoperability`

Script:

> Hi, I'm Dexter Pressley, and I worked on LLM interoperability across the platform.  
> That matters because a serious system cannot be locked to one model or provider if you want both vendor flexibility and research-grade comparisons.

### 1:20-1:35 - Andrew First Appearance

Visuals:

- Andrew on camera
- lower third: `Andrew Chambers | Benchmarking and Evaluation`

Script:

> Hi, I'm Andrew Chambers, and I led benchmarking and evaluation for the project.  
> That matters because a platform like this should be measurable on controlled workloads, not just shown through handpicked examples.

### 1:35-1:50 - Sammy First Appearance

Visuals:

- Sammy on camera
- lower third: `Sammy Fares | Retrieval-Augmented Generation`

Script:

> Hi, I'm Sammy Fares, and I built the retrieval-augmented generation component.  
> That matters because real engineering benefits from reusable prior knowledge, especially when multi-module designs share familiar patterns.

### 1:50-2:05 - Caleb First Appearance

Visuals:

- Caleb on camera
- lower third: `Caleb Elliott | Observability and Cost`

Script:

> Hi, I'm Caleb Elliott, and I worked on observability and cost accounting for the platform.  
> That matters because engineering teams and researchers both need traceability, not just outputs.

### 2:05-2:20 - Matheus First Appearance

Visuals:

- Matheus on camera
- lower third: `Mateus Verffel Mayer | Tooling and EDA Integration`

Script:

> Hi, I'm Mateus Verffel Mayer, and I worked on tooling, environment integration, and EDA tool connectivity.  
> That matters because an agent system is only useful if it can actually drive real EDA tools instead of stopping at text generation.

### 2:20-3:05 - Architecture And Novelty

Speaker: Jacobo

Visuals:

- architecture slide with 7 boxes:
  - `Spec Input`
  - `Planner`
  - `DAG + Design Context`
  - `Agent Roles`
  - `EDA Tool Workers`
  - `Benchmarking`
  - `Observability + Cost`

Script:

> What makes this project interesting is not any one feature in isolation.  
> The novelty is the combination.  
> The system freezes intent into a design context, schedules execution through an orchestrator, supports configurable model backends, augments context with retrieval, runs external tools, and then exposes benchmark and observability artifacts for inspection.  
> That makes it both an engineering workflow and a research platform.

### 3:05-3:30 - Testing Plan And Feedback

Speaker: Andrew

Visuals:

- slide titled `How Feedback Changed Our Testing Plan`
- bullets:
  - `more measurable results`
  - `repeatable benchmark runs`
  - `clearer observability`

Script:

> Based on earlier reviews and our own rehearsals, we pushed the testing plan toward evidence.  
> We strengthened repeatable benchmark runs, clearer observability, and better prepared proof artifacts, so the project could be judged on measurable behavior rather than a single happy-path demo.

### 3:30-4:05 - Strongest Evidence

Speaker: Andrew and Caleb split this section

Visuals:

- result slide with 3 callouts:
  - `156-case canonical benchmark: 73.72% pass rate`
  - `10-case prepared retest: 10/10`
  - `run-scoped token and cost summaries`

Script for Andrew:

> On the research side, one full canonical benchmark run in our stored artifacts reached a 73.72 percent pass rate over 156 cases.  
> For a prepared reproducibility slice, a 10-case retest reached 10 out of 10.

Script for Caleb:

> On the systems side, every run can emit token, cost, and stage-level observability artifacts, so the evidence is not just whether it worked, but how it behaved.

### 4:05-4:23 - Jacobo Second Appearance

Visuals:

- Jacobo on camera for a few seconds
- then proof visual:
  - `artifacts/generated/dag.json`
  - `artifacts/generated/design_context.json`

Script:

> Here the planner outputs a multi-module DAG and a structured design context.  
> That is the core proof that orchestration is based on explicit contracts and dependencies, not a vague prompt chain.

### 4:23-4:41 - Dexter Second Appearance

Visuals:

- Dexter on camera for a few seconds
- then proof visual:
  - `config/domains/agents.yaml`

Script:

> This configuration is the proof of model interoperability.  
> We can change defaults, override roles, and tune settings like temperature and token budgets without redesigning the system around one provider.

### 4:41-4:59 - Andrew Second Appearance

Visuals:

- Andrew on camera for a few seconds
- then proof visual:
  - `artifacts/benchmarks/verilog_eval/canonical_full_156/aggregate.json`
  - `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_20260323_retest2/canonical/aggregate.json`

Script:

> These aggregate artifacts are the proof that the system can be evaluated as a benchmarked platform.  
> We are showing stored outputs here because the interesting part is the evidence, not spending video time waiting for commands to finish.

### 4:59-5:17 - Sammy Second Appearance

Visuals:

- Sammy on camera for a few seconds
- then proof visual:
  - `artifacts/rag/memory.json`
  - optional run clip with `--rag on`

Script:

> This is the proof that retrieval is part of the engineering flow.  
> The system can consult curated design memory when it helps, which is especially useful when design knowledge is reusable across modules or runs.

### 5:17-5:35 - Caleb Second Appearance

Visuals:

- Caleb on camera for a few seconds
- then proof visual:
  - `artifacts/observability/demo_retest_counter3_basic_20260323_summary.json`
  - `artifacts/observability/benchmark_demo_readiness_smoke10_20260323_retest2_canonical_summary.json`

Script:

> These summaries are the proof that we track usage and cost at run scope.  
> For example, our prepared counter retest and benchmark retest each carry concrete token and estimated-cost totals, which makes comparison and debugging much more disciplined.

### 5:35-5:50 - Matheus Second Appearance

Visuals:

- Matheus on camera for a few seconds
- then proof visual:
  - `tool_registry.yaml`
  - optional terminal or log clip with `iverilog`, `vvp`, or `verilator`

Script:

> This tooling layer is the proof that the system connects to real EDA infrastructure.  
> The registry and workers turn the agent stack into an actual engineering pipeline instead of a text-only assistant.

### 5:50-6:25 - Industry Value

Speaker: Jacobo

Visuals:

- slide titled `Why Industry Should Care`
- bullets:
  - `shorter spec-to-verification loop`
  - `less manual handoff friction`
  - `traceable tool and cost behavior`

Script:

> From an industry perspective, the value is not novelty for its own sake.  
> The value is reducing the time and friction between design intent and verified artifacts while keeping the process inspectable.  
> Planning, tool integration, and observability are what make that useful in a real engineering environment.

### 6:25-7:05 - Research Value

Speaker: Andrew

Visuals:

- slide titled `Why Research Should Care`
- bullets:
  - `benchmarkable`
  - `model-agnostic`
  - `artifact-rich`

Script:

> From a research perspective, the key contribution is that this is not a black-box demo.  
> It is benchmarkable, model-agnostic, and artifact-rich.  
> That means we can study how agent structure, model choice, retrieval, and tool interaction affect outcomes with real evidence.

### 7:05-8:20 - Broader Impact And Team Close

Speaker: Jacobo with brief cutaways to all members

Visuals:

- montage of all 6 members
- architecture, benchmark, cost, and tool visuals reused briefly

Script:

> The broader impact of this project is that it connects two worlds that are often separated.  
> For engineering teams, it offers a more structured and inspectable path from spec to verified hardware artifacts.  
> For researchers, it offers a platform for evaluating agentic hardware-design workflows with reproducible evidence.  
> That combination is what we believe makes this project both practical and novel.

### 8:20-9:00 - Final Close

Speaker: Jacobo

Visuals:

- final title card with all names

Script:

> This project is a multi-agent hardware design platform that combines orchestration, interoperability, retrieval, benchmarking, observability, and tool integration into one repeatable system.  
> Thank you for watching.

## Assets To Use

## High-Signal Proof Visuals

These are the visuals worth spending time on.

### Orchestration

- `artifacts/generated/dag.json`
- `artifacts/generated/design_context.json`

### Interoperability

- `config/domains/agents.yaml`
- optional: `docs/components/llm-gateway.md`

### Benchmark Evidence

- `artifacts/benchmarks/verilog_eval/canonical_full_156/aggregate.json`
- `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_20260323_retest2/canonical/aggregate.json`

### RAG

- `artifacts/rag/memory.json`
- optional short clip of a run with `--rag on`

### Observability And Cost

- `artifacts/observability/demo_retest_counter3_basic_20260323_summary.json`
- `artifacts/observability/benchmark_demo_readiness_smoke10_20260323_retest2_canonical_summary.json`
- optional AgentOps dashboard screenshot if you already have one

### Tool Integration

- `tool_registry.yaml`
- optional terminal/log clip showing `iverilog`, `vvp`, or `verilator`

## Slides To Create

Make these in Google Slides, Keynote, or Canva and export as PNG.

### Slide 1 - Title

Text:

- `MHD: Multi-Agent Hardware Design System`
- `Senior Design Showcase`
- team names

### Slide 2 - Why This Matters

Text:

- `Industry: shorter path from spec to verified artifact`
- `Research: benchmarkable agentic hardware-design workflow`

### Slide 3 - Architecture

Boxes:

- `Spec Input`
- `Planner`
- `DAG + Design Context`
- `Agent Roles`
- `EDA Tool Workers`
- `Benchmarking`
- `Observability + Cost`

### Slide 4 - Evidence

Text:

- `156-case canonical benchmark: 73.72%`
- `10-case prepared retest: 10/10`
- `run-scoped token and cost evidence`

### Slide 5 - Industry Value

Text:

- `planning-first execution`
- `tool-integrated workflow`
- `traceable outputs`

### Slide 6 - Research Value

Text:

- `benchmarkable`
- `model-agnostic`
- `artifact-rich`

### Slide 7 - Closing

Text:

- `Orchestration`
- `Interoperability`
- `RAG`
- `Benchmarking`
- `Observability`
- `EDA Integration`

## What Not To Waste Time On

- long command walkthroughs
- typing live in the terminal for more than a few seconds
- stock video
- custom logo animations
- AI-generated filler visuals
- complex transitions
- anything that does not strengthen novelty, evidence, or impact

## Fastest Editing Plan

1. Collect all talking-head clips.
2. Collect only a few short proof visuals per subsystem.
3. Build the 7 slides above.
4. Edit in iMovie.
5. Use hard cuts and simple lower-thirds.
6. Use screenshot pans or Ken Burns on still images when a full screen recording is unnecessary.
7. Keep technical visuals on screen long enough to read.
8. Export at `1080p`.
9. Upload to YouTube as `Unlisted`.
10. Wait for automatic captions.
11. Fix technical terms manually.

## Recommended Tools

Primary recommendation:

- `iMovie` for editing
- `QuickTime Player` for Mac screen capture
- `OBS` only if someone is recording on PC or wants webcam + screen at once

This is the best speed-to-quality tradeoff for your constraints.

## Official Tool Links

- iMovie support: <https://support.apple.com/imovie>
- create a movie in iMovie: <https://support.apple.com/en-us/HT210410>
- add titles in iMovie: <https://support.apple.com/en-us/102340>
- QuickTime screen recording on Mac: <https://support.apple.com/guide/quicktime-player/record-your-screen-qtp97b08e666/mac>
- OBS: <https://obsproject.com/>
- DaVinci Resolve: <https://www.blackmagicdesign.com/products/davinciresolve>
- YouTube captions: <https://support.google.com/youtube/answer/2734796?hl=en>
- YouTube automatic captions: <https://support.google.com/youtube/answer/6373554?hl=en>

## Final Guidance

- The judges care more about significance and credibility than workflow minutiae.
- Keep the visuals proof-oriented.
- Use the team members as specialists explaining why each subsystem matters.
- Treat commands as supporting evidence, not the centerpiece.
