# LLM Gateway Component

## Purpose
Explain how model providers are selected and invoked for agent runtime calls.

## Audience
Engineers changing provider adapters, model settings, or LLM error handling.

## Scope
Gateway initialization, provider selection, and adapter behavior.

## Current Providers
- OpenAI adapter
- Groq adapter
- Optional local Qwen adapter utilities (kept as legacy/optional tooling)

## Selection Rules
- Runtime config selects provider/model defaults.
- Secret presence gates initialization (missing key => gateway unavailable).
- Agents should fail explicitly when LLM is required but unavailable.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/agents/common/llm_gateway.py`
- `/home/jacobo/school/FPGA_Design_Agent/adapters/llm/`
- `/home/jacobo/school/FPGA_Design_Agent/core/runtime/config.py`

## Related Docs
- [../agents.md](../agents.md)
- [../reference/runtime-config.md](../reference/runtime-config.md)
