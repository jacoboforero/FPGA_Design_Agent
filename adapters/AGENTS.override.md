# Adapters Override

- Adapter changes should preserve env-driven configuration, provider normalization, and error surfaces expected by callers.
- Keep provider-specific behavior inside `adapters/`; do not leak it upward into agents, CLI flows, or schemas unless the task explicitly requires a new shared contract.
- If you touch LLM request or response shaping, review the impact on cost tracking, retries, and fallback behavior.
- If you touch RAG code, preserve the current boundary between retrieval, prompting, and narration unless the task explicitly changes it.
- Typical validation:
- `pytest tests/adapters -q`
- `pytest tests/agents/test_common_llm_gateway.py -q`
- run the closest CLI or execution tests if adapter behavior is user-visible
