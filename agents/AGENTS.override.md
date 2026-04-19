# Agents Override

- Agent worker changes must remain compatible with orchestrator expectations, task routing, and `ResultMessage` payload shape.
- Prefer prompt edits in `prompts/` when the change is instruction quality or output framing rather than control flow or parsing logic.
- Preserve structured output parsing and repair paths. If you relax validation, pair it with tests.
- Avoid embedding benchmark-specific or scenario-specific behavior directly in agent logic unless that behavior is already part of shared configuration.
- Typical validation:
- `pytest tests/agents -q`
- `pytest tests/apps -q`
- `pytest tests/execution -q`
- `pytest tests/orchestrator -q` when handoff or retry behavior changes
