# LLM Gateway Component

The LLM gateway provides provider/model abstraction for agent workers.

## Supported Providers
- OpenAI adapter
- Groq adapter
- Optional local/experimental adapters

## Selection And Initialization
- Provider/model defaults come from runtime config.
- Provider credentials come from environment variables.
- If credentials are missing, LLM-dependent agents return explicit failure instead of silently degrading.

## Reliability Notes
- Agent workers should treat gateway unavailability as a clear task failure.
- Retry behavior is controlled by caller/runtime policy, not by hidden gateway loops.

## Related Code
- `agents/common/llm_gateway.py`
- `adapters/llm/`
- `core/runtime/config.py`
