# Aspirational Integration Tests

These tests document desired integration behaviors that require more sophisticated test infrastructure (proper mock sequencing at import time) to fully validate. They are preserved here as a requirements/specification document for future enhancement of the integration test suite.

## Test Categories & Scenarios

### 1. Gateway Adapter Integration (12 scenarios)

**Legacy Mode Initialization:**
- Verify legacy mode with OpenAI creates correct adapter
- Verify legacy mode with Anthropic creates correct adapter  
- Verify legacy mode with Groq creates correct adapter

**Response Handling:**
- OpenAI adapter receives response and converts it correctly
- Anthropic adapter receives response and converts it correctly

**Error Cases:**
- Missing API key returns None
- Invalid provider returns None

**Config Mode:** (removed) — centralized `gateway_config` feature has been removed; use legacy environment-variable initialization via `init_llm_gateway()`.

**Config Mode Precedence:**
- Legacy mode is default (even with GATEWAY_TIER set)
- Centralized config-mode behavior has been removed; legacy env-vars apply.
- USE_LLM=0 disables LLM regardless of other config

**Fallback Initialization:**
- Tiered fallback chains and config-mode fallback have been removed (legacy init only).

---

### 2. Message Pipeline Formatting (17 scenarios)

**OpenAI Formatting:**
- Simple user message passed correctly to OpenAI
- System message included in OpenAI request
- Multi-turn conversation properly formatted for OpenAI

**Anthropic Formatting:**
- System message separated for Anthropic (moved to system parameter)
- User message correctly formatted for Anthropic  
- Multi-turn conversation with assistant responses

**Cohere Formatting (Uppercase Roles):**
- User role converted to USER for Cohere
- Assistant role converted to CHATBOT for Cohere

**Google Gemini Formatting:**
- Assistant role converted to "model" for Google Gemini

**Complex Content:**
- Empty user message handling
- Long user message (5000+ chars) passed without truncation
- Special characters preserved (Unicode, emojis, newlines)

---

### 3. Adapter Switching & Per-Agent Configuration (20 scenarios)

**Per-Agent Overrides:**
- DEFAULT_LLM_PROVIDER used as default provider
- DEFAULT_LLM_MODEL used as default model
- Per-agent override ignored without agent_type parameter
- Multiple agent types can use different providers simultaneously
- Per-agent override requires valid API key

**Adapter Switching:**
- Can switch from OpenAI to Anthropic
- Can switch models within same provider
- Each agent gets its configured adapter (simultaneous testing)

**Per-Agent Models:**
- Per-agent model configuration with OpenAI
- Per-agent both provider and model override

**Environment Isolation:**
- Agent isolation: one call doesn't affect another
- Changing per-agent env var affects new initialization

---

### 4. Environment Variable Precedence (17 scenarios)

**Legacy Mode:**
- DEFAULT_LLM_PROVIDER env var used in legacy mode
- DEFAULT_LLM_MODEL env var used in legacy mode
- USE_LLM=0 disables LLM
- USE_LLM=1 enables LLM

**Config Mode:**
- Centralized gateway_config removed; legacy env-vars are used
- GATEWAY_TIER env var selects adapter
- Invalid tier returns None
- Config mode removed (no USE_GATEWAY_CONFIG flag)

**Precedence Order:**
- Legacy mode takes precedence over config (when both set)
- Centralized config-mode has been removed; legacy env-vars apply
- Per-agent override takes precedence over default provider
- Per-agent override takes precedence over default model

**Tier Mapping:**
- FAST tier maps to expected provider (Groq)
- BALANCED tier maps to expected provider (Anthropic)  
- QUALITY tier maps to expected provider (OpenAI)
- Agent-specific GATEWAY_TIER_{agent_type} overrides

**Consistency:**
- Same config returns same provider on subsequent calls
- Changed config changes provider on new init
- Agent-type config doesn't affect other agents

**Defaults:**
- Default model used when DEFAULT_LLM_MODEL not specified
- Default tier used when GATEWAY_TIER not specified

---

### 5. Error Propagation & Recovery (16 scenarios)

**Missing Configuration:**
- Missing OpenAI API key returns None
- Missing Anthropic API key returns None
- Missing Groq API key returns None
- Missing DEFAULT_LLM_PROVIDER env var returns None

**Invalid Configuration:**
- Invalid provider returns None
- Empty provider string returns None
- Case-insensitive provider handling works

**Adapter Initialization Errors:**
- Adapter init exception returns None
- Anthropic init exception returns None
- Per-agent adapter init failure returns None (default succeeds)

**Generation Errors:**
- OpenAI API error propagates correctly
- Anthropic API error propagates correctly
- Empty messages list handled gracefully

**Error Recovery:**
- Failed init (missing API key) followed by successful init works
- Can fallback to different provider on failure

**Partial Configuration:**
- Per-agent override with missing API key returns None (default works)
- Per-agent model without provider override works

---

## Implementation Strategy for Future

### Challenge
Tests fail because mocks are applied AFTER imports occur. Standard mocking (`mocker.patch()`) happens after `init_llm_gateway()` tries to import adapter modules.

### Solutions Evaluated

**Option 1: Early Mock Application**
- Establish mocks in fixtures before any test code runs
- Requires comprehensive fixture setup for all providers
- Creates fixture interdependencies

**Option 2: Module-Level Mocking**
- Patch `sys.modules` at test collection time
- Use `autouse=True` fixtures
- Affects all tests (even ones needing None behavior)

**Option 3: Adapter Registry Pattern**
- Refactor production code to use adapter registry
- Tests inject mocks via registry
- Requires architectural changes to codebase

**Option 4: Focused Behavior Testing** ← CURRENT RECOMMENDATION
- Test configuration reading directly
- Test message conversion in isolation
- Test error handling independently
- Keep aspirational tests as specification

### Next Steps
1. Implement Option 4 with 10-15 focused tests
2. Reference this document when considering Option 1, 2, or 3
3. When expanding integration coverage, start with specific behaviors
4. Only implement full gateway initialization tests if critical to business logic

---

## Value & Reference

These scenarios document:
- ✅ Complete integration test coverage surface area
- ✅ Expected behavior for all gateway modes
- ✅ Message formatting requirements per provider
- ✅ Configuration precedence rules
- ✅ Error handling contracts

Use this as a specification when:
- Reviewing gateway architecture changes
- Designing adapter interface modifications  
- Planning future integration test improvements
- Validating configuration system behavior
