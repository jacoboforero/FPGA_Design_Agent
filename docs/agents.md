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
  - Outputs: patched RTL and/or TB written to the target paths + a structured rationale report
  - Success: interface preserved, code written, rationale persisted to task memory

## Interaction rules
- All work is brokered; agents never call each other directly.
- On unrecoverable inputs (schema/interface mismatch), reject to DLQ. Retry only once for transient LLM/tool errors.
- Keep context size modest to avoid blowing token windows; prefer concise summaries over full logs unless debugging.

### Per-agent LLM selection
- Canonical env var format (required): `{AGENT}_LLM_PROVIDER` and `{AGENT}_LLM_MODEL` (e.g., `SPEC_HELPER_LLM_MODEL`). This groups settings by agent when scanning `.env` files.
- Legacy suffix-style (`LLM_PROVIDER_{agent}` / `LLM_MODEL_{agent}`) has been removed and is ignored.
- Supported agent names: `planner`, `implementation`, `testbench`, `debug`, `reflection`, `spec_helper`.
- Note (Ollama/local Qwen): running multiple instances of the program that point at the same Ollama daemon can serialize or contend LLM calls. To avoid contention, run separate Ollama daemons on different ports and set `OLLAMA_BASE_URL` per run.
- Example mapping for the requested setup:
  - `DEBUG_LLM_PROVIDER=openai` and `DEBUG_LLM_MODEL=gpt-5.2`
  - `IMPLEMENTATION_LLM_PROVIDER=openai` and `IMPLEMENTATION_LLM_MODEL=gpt-5.2`
  - `PLANNER_LLM_PROVIDER=qwen-local`
  - `REFLECTION_LLM_PROVIDER=anthropic` and `REFLECTION_LLM_MODEL=claude-haiku-4-5-...`
