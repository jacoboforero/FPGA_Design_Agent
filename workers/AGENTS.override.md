# Workers Override

- Workers are deterministic execution stages. Keep them free of hidden LLM or network behavior unless the task explicitly changes that boundary.
- Preserve artifact paths, log capture, retry semantics, and failure signaling expected by the orchestrator and reporting flows.
- Keep validation explicit and fail with actionable errors rather than silent fallbacks.
- Avoid hardcoded machine-specific paths or assumptions that break Docker and host parity.
- Typical validation:
- `pytest tests/workers -q`
- `pytest tests/execution -q`
- `pytest tests/infrastructure -q` when queueing or broker interaction changes
