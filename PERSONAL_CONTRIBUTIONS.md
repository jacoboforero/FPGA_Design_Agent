# Personal Contributions

FPGA Design Agent was built as a 6-person senior capstone and research
prototype. My primary contribution was designing and implementing the core
spec-to-verified-Verilog workflow; I also coordinated the roadmap and execution
for the year-long team effort.

## What I Owned

- Designed the planning-first system shape: specification intake and
  refinement, structured planning artifacts, execution-ready design context,
  and verification-first RTL generation.
- Translated background research into concrete system goals, architecture,
  roadmap, milestones, and implementation work for the team.
- Implemented the main CLI flow for interactive engineer runs, benchmark runs,
  environment checks, run configuration, narration, and demo workflows.
- Implemented the orchestrator, state transitions, DAG execution behavior,
  retry policy, failure propagation, task memory recording, and run-scoped
  result handling.
- Implemented the RabbitMQ-backed task/result routing model used by agents,
  deterministic workers, and the orchestrator.
- Implemented the LLM-backed agent runtimes for planning, specification help,
  RTL implementation, testbench generation, reflection, debug, and finalization.
- Designed and implemented the prompt engineering and structured output
  expectations used across the agent stages.
- Implemented deterministic workers that interface with EDA tools, including
  linting, testbench linting, simulation, acceptance checks, and failure
  distillation.
- Implemented and ran the VerilogEval v2-backed benchmark harness, including
  benchmark discovery, execution modes, result aggregation, comparison, and
  artifact reporting.
- Worked across documentation, demo readiness, benchmark methodology,
  observability, packaging, and repo-level positioning.

## Areas Primarily Owned By Teammates

- The original external LLM provider adapter implementations.
- The initial RAG system implementation.
- The initial tool registry file.

I still touched parts of these areas during integration and refinement, including
small RAG-related changes, but they were not my primary ownership areas. I have
built LLM API integrations and retrieval workflows in other projects.

## Why This Matters

The project reflects the kind of engineering work I want to do professionally:
agentic AI developer tools for chip-design, EDA, and technical engineering
workflows. My contribution was not limited to coordination or isolated feature
work; I designed and implemented the core execution platform that connects
planning, agent work, deterministic EDA checks, repair loops, benchmark
reporting, and developer-facing CLI workflows.
