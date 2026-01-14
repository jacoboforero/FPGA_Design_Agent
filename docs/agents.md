# Agents (roles and IO)

All agents run inside the agent-worker runtime and are selected by `AgentType`. They read the frozen design context and write artifacts/logs to task memory. Keep inputs lean; log model/tool choices when LLMs are used.

## Planning
- **Spec Helper** — guides L1–L5, asks clarifying questions, and produces the locked checklist under `artifacts/task_memory/specs/`.
- **Planner** — consumes locked specs and emits `design_context.json` + `dag.json`.

## Execution
- **Implementation**
  - Inputs: interface signals, spec summary/demobehavior, target `rtl_path`
  - Outputs: RTL file + log (model/assumptions)
  - Success: file exists, ports match interface
- **Testbench**
  - Inputs: interface signals, test goals/coverage hints, target `testbench_path`
  - Outputs: TB file + log of scenarios
  - Success: TB instantiates DUT and drives ports
- **Reflection**
  - Inputs: distilled dataset path and/or sim log
  - Outputs: structured insights (hypotheses, likely failure points, probes)
  - Success: non-empty insights
- **Debug**
  - Inputs: failing RTL/TB context, reflection insights, failure signature
  - Outputs: patched RTL/TB (or justified no-op) + rationale
  - Success: interface preserved and changes explained

## Interaction rules
- All work is brokered; agents never call each other directly.
- On unrecoverable inputs (schema/interface mismatch), reject to DLQ. Retry only once for transient LLM/tool errors.
- Keep context size modest to avoid blowing token windows; prefer concise summaries over full logs unless debugging.
