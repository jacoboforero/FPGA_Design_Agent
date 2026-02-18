# OpenAI implementation of the LLM Gateway interface.

from typing import Optional, List
import logging
from openai import AsyncOpenAI
from adapters.llm.gateway import (
    LLMGateway,
    Message,
    MessageRole,
    ModelResponse,
    GenerationConfig,
)

logger = logging.getLogger(__name__)


class OpenAIGateway(LLMGateway):
    
    # Pricing must currently be manually maintained. Price per million tokens.
    PRICING = {
        # Very-High-Cost Model "gpt-5-pro": {"input": 15.00, "output": 120.00},

        # GPT-5 family (include new 5.1 / 5.2 variants)
        "gpt-5.2": {"input": 1.50, "output": 12.00},
        "gpt-5.1": {"input": 1.25, "output": 10.00},
        "gpt-5": {"input": 1.25, "output": 10.00},
        "gpt-5-mini": {"input": 0.25, "output": 2.00},
        "gpt-5-nano": {"input": 0.05, "output": 0.40},

        # Codex / completions (code-focused models) — only modern `gpt-*-codex` models are supported
        "gpt-5.3-codex": {"input": 1.75, "output": 14.00},
        "gpt-5.3-codex-spark": {"input": 0.75, "output": 5.00},
        "gpt-5.2-codex": {"input": 1.50, "output": 12.00},
        "gpt-5-codex-mini": {"input": 0.25, "output": 2.00},
        "gpt-5.1-codex-max": {"input": 2.00, "output": 16.00},

        # GPT-4.1 family
        "gpt-4.1": {"input": 2.00, "output": 8.00},
        "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
        "gpt-4.1-nano": {"input": 0.10, "output": 0.40},

        # GPT-4o family
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},

        # LEGACY "gpt-3.5-turbo": {"input": 0.5, "output": 1.5}
    }
    

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5-nano",
        organization: Optional[str] = None, # Required for billing, rate limits, usage reports.
    ):
        self.client = AsyncOpenAI(
            api_key=api_key,
            organization=organization,
        )
        self._model = model
        self.logger = logger
    
    async def generate(
        self,
        messages: List[Message],
        config: Optional[GenerationConfig] = None,
    ) -> ModelResponse:
        """Generate a response using OpenAI's chat completion API."""
        config = config or GenerationConfig()
        config = self.validate_config(config)
        
        # Convert our Message format to OpenAI's format
        openai_messages = self._convert_messages(messages)

        # Helper: flatten messages into a single prompt for non-chat endpoints
        prompt_text = "\n\n".join([m.content for m in messages])

        # Common chat params (used for Chat Completions path)
        chat_api_params = {
            "model": self._model,
            "messages": openai_messages,
        }

        # Add optional parameters (chat + common)
        if config.temperature is not None:
            chat_api_params["temperature"] = config.temperature
        if config.top_p is not None:
            chat_api_params["top_p"] = config.top_p
        if config.max_tokens is not None:
            chat_api_params["max_tokens"] = config.max_tokens
        if config.stop_sequences:
            chat_api_params["stop"] = config.stop_sequences

        # Pass through commonly used provider features (typed fields)
        if getattr(config, "functions", None) is not None:
            chat_api_params["functions"] = config.functions
        if getattr(config, "function_call", None) is not None:
            chat_api_params["function_call"] = config.function_call
        if getattr(config, "n", None) is not None:
            chat_api_params["n"] = config.n
        if getattr(config, "logprobs", None) is not None:
            chat_api_params["logprobs"] = config.logprobs
        if getattr(config, "user", None) is not None:
            chat_api_params["user"] = config.user
        if getattr(config, "stream", None) is not None:
            chat_api_params["stream"] = config.stream

        # Prepare completion (Codex/legacy completions API) params when needed
        completion_api_params = {
            "model": self._model,
            "prompt": prompt_text,
        }
        if config.temperature is not None:
            completion_api_params["temperature"] = config.temperature
        if config.top_p is not None:
            completion_api_params["top_p"] = config.top_p
        if config.max_tokens is not None:
            completion_api_params["max_tokens"] = config.max_tokens
        if config.stop_sequences:
            completion_api_params["stop"] = config.stop_sequences
        if getattr(config, "n", None) is not None:
            completion_api_params["n"] = config.n
        if getattr(config, "logprobs", None) is not None:
            completion_api_params["logprobs"] = config.logprobs
        if getattr(config, "user", None) is not None:
            completion_api_params["user"] = config.user

        # Add provider-specific parameters (lowest-precedence passthrough)
        chat_api_params.update(config.provider_specific)
        completion_api_params.update(config.provider_specific)

        try:
            # 1) Responses API (explicit opt-in)
            if getattr(config, "use_responses_api", False):
                response = await self.client.responses.create(model=self._model, input=prompt_text, **config.provider_specific)

            # 2) Explicit completions opt-in OR model indicates modern Codex (models that contain 'codex')
            elif getattr(config, "use_completions_api", False) or ("codex" in (self._model or "")):
                # Route to the completions (Codex) endpoint for models that explicitly include 'codex'
                response = await self.client.completions.create(**completion_api_params)

            # 3) Default: Chat Completions
            else:
                response = await self.client.chat.completions.create(**chat_api_params)

            # Normalize to ModelResponse
            model_response = self._convert_response(response)
            return model_response
            
        except Exception as e:
            error_msg = str(e).lower()
            if "rate" in error_msg or "limit" in error_msg:
                raise RuntimeError(f"OpenAI rate limit exceeded: {e}")
            elif "quota" in error_msg or "insufficient" in error_msg:
                raise RuntimeError(f"OpenAI quota exceeded: {e}")
            elif "invalid" in error_msg and "key" in error_msg:
                raise RuntimeError(f"OpenAI authentication failed: {e}")
            else:
                raise RuntimeError(f"OpenAI API error: {e}")
    
    @property
    def model_name(self) -> str:
        """The OpenAI model being used."""
        return self._model
    
    @property
    def provider(self) -> str:
        """Returns 'openai'."""
        return "openai"
    
    @property
    def supports_files(self) -> bool:
        """OpenAI supports vision/files for GPT-4 vision models."""
        return "vision" in self._model or "gpt-4o" in self._model
    
    def validate_config(self, config: GenerationConfig) -> GenerationConfig:
        """
        Validate configuration for OpenAI.
        
        OpenAI constraints:
        - temperature: [0, 2]
        - top_p: [0, 1]
        - Can use both temperature and top_p (OpenAI recommends altering one, not both)
        - top_k not supported
        """
        if config.temperature is not None:
            if not 0 <= config.temperature <= 2:
                raise ValueError("OpenAI temperature must be in [0, 2]")
        
        if config.top_p is not None:
            if not 0 <= config.top_p <= 1:
                raise ValueError("OpenAI top_p must be in [0, 1]")
        
        if config.top_k is not None:
            raise ValueError("OpenAI does not support top_k parameter")
        
        if config.temperature is not None and config.top_p is not None:
            # OpenAI docs recommend not using both, but allow it
            self.logger.warning(
                "Using both temperature and top_p. OpenAI recommends using only one."
            )
        
        return config
    
    def estimate_cost(self, response: ModelResponse) -> float:
        """
        Estimate cost based on OpenAI pricing.
        
        Returns cost in USD.
        """
        # Find matching pricing model (handle versioned models)
        # Sort by length descending to match most specific first
        pricing_key = None
        model_families = sorted(self.PRICING.keys(), key=len, reverse=True)
        
        for family in model_families:
            if family in response.model_name:
                pricing_key = family
                break
        
        if not pricing_key:
            self.logger.warning(f"Unknown OpenAI model for pricing: {response.model_name}")
            return 0.0  # Unknown model, can't estimate
        
        pricing = self.PRICING[pricing_key]
        
        # Pricing is per 1M tokens
        input_cost = (response.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (response.output_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    def _convert_messages(self, messages: List[Message]) -> List[dict]:
        """Convert our Message format to OpenAI's format."""
        openai_messages = []
        
        for msg in messages:
            openai_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            
            # Handle file attachments - append their text content to the message
            if msg.attachments:
                file_contents = []
                for attachment in msg.attachments:
                    if "content" in attachment:
                        filename = attachment.get("filename", "file")
                        file_contents.append(f"\n\n--- {filename} ---\n{attachment['content']}")
                    elif "path" in attachment:
                        try:
                            with open(attachment["path"], "r", encoding="utf-8") as f:
                                content = f.read()
                                filename = attachment.get("filename", attachment["path"])
                                file_contents.append(f"\n\n--- {filename} ---\n{content}")
                        except Exception as e:
                            self.logger.error(f"Error reading attachment {attachment['path']}: {e}")
                            file_contents.append(f"\n\n[Error reading {attachment.get('filename', 'file')}: {e}]")
                
                if file_contents:
                    openai_msg["content"] = msg.content + "".join(file_contents)
            
            openai_messages.append(openai_msg)
        
        return openai_messages
    
    def _convert_response(self, openai_response) -> ModelResponse:
        """Convert OpenAI response to our ModelResponse format."""
        # Normalize several possible OpenAI response shapes (Chat, Completions, Responses API)
        choice = None
        content = ""

        # Helper: accept only plain dict/list structures; ignore MagicMock-like objects
        def _as_dict(val):
            if isinstance(val, dict):
                return val
            try:
                if hasattr(val, "model_dump"):
                    dumped = val.model_dump()
                    if isinstance(dumped, dict):
                        return dumped
                if hasattr(val, "to_dict"):
                    dumped = val.to_dict()
                    if isinstance(dumped, dict):
                        return dumped
            except Exception:
                return None
            return None

        # Chat / Completions: choices list exists and is a concrete list
        choices_attr = None
        if isinstance(openai_response, dict):
            choices_attr = openai_response.get("choices")
        else:
            choices_attr = getattr(openai_response, "choices", None)

        if isinstance(choices_attr, list) and choices_attr:
            choice = choices_attr[0]

            # If the choice is a plain dict, prefer dictionary access
            if isinstance(choice, dict):
                content = (
                    choice.get("message", {}) and choice.get("message", {}).get("content")
                ) or choice.get("text") or ""
            else:
                # Attempt safe extraction from SDK objects (avoid returning MagicMock-like attrs)
                msg = getattr(choice, "message", None)
                if msg is not None and hasattr(msg, "content"):
                    try:
                        raw_content = msg.content
                        if isinstance(raw_content, str):
                            content = raw_content
                    except Exception:
                        pass

                if not content:
                    msg_dict = _as_dict(msg) if msg is not None else None
                    if isinstance(msg_dict, dict) and msg_dict.get("content"):
                        content = msg_dict.get("content")
                    else:
                        txt = getattr(choice, "text", None)
                        if isinstance(txt, str):
                            content = txt
                        else:
                            # Fallback: try converting choice via model_dump/to_dict
                            choice_dict = _as_dict(choice)
                            if isinstance(choice_dict, dict):
                                content = (
                                    choice_dict.get("message", {}) and choice_dict.get("message", {}).get("content")
                                ) or choice_dict.get("text") or ""
                            else:
                                content = ""

            # Extract usage when present (only accept concrete mappings or SDK usage objects)
            usage = None
            if isinstance(openai_response, dict):
                usage = openai_response.get("usage")
            else:
                usage = getattr(openai_response, "usage", None)

            input_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
            if isinstance(input_tokens, int) is False:
                input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else 0

            output_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
            if isinstance(output_tokens, int) is False:
                output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else 0

            total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None
            if isinstance(total_tokens, int) is False:
                total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else (input_tokens + output_tokens)

        # Responses API: `output` field with structured content
        elif hasattr(openai_response, "output") or (isinstance(openai_response, dict) and openai_response.get("output")):
            raw_out = getattr(openai_response, "output", None) or openai_response.get("output")
            # Try common locations for plain text content
            try:
                if isinstance(raw_out, list) and raw_out:
                    first = raw_out[0]
                    # structure: {"content": [{"type":"output_text","text":"..."}]}
                    if isinstance(first, dict):
                        content_items = first.get("content") or first.get("contents")
                        if isinstance(content_items, list) and content_items:
                            # find first text-like item
                            for ci in content_items:
                                if isinstance(ci, dict) and (ci.get("text") or ci.get("type") == "output_text"):
                                    content = ci.get("text") or ci.get("text") or content
                                    break
                        else:
                            content = first.get("text") or ""
            except Exception:
                content = ""

            usage = getattr(openai_response, "usage", None) or (openai_response if isinstance(openai_response, dict) and openai_response.get("usage") else None)
            input_tokens = getattr(usage, "prompt_tokens", None) or (usage.get("prompt_tokens") if isinstance(usage, dict) else 0)
            output_tokens = getattr(usage, "completion_tokens", None) or (usage.get("completion_tokens") if isinstance(usage, dict) else 0)
            total_tokens = getattr(usage, "total_tokens", None) or (usage.get("total_tokens") if isinstance(usage, dict) else input_tokens + output_tokens)

        else:
            # Unknown shape — best-effort stringification
            try:
                content = str(openai_response)
            except Exception:
                content = ""

            input_tokens = 0
            output_tokens = 0
            total_tokens = 0

        # Warn if token counts seem wrong
        if input_tokens == 0 or output_tokens == 0:
            self.logger.warning(
                f"Unusual token counts from OpenAI: "
                f"input={input_tokens}, output={output_tokens}"
            )

        # Pull out structured extras (function_call, logprobs, raw choices)
        function_call = None
        logprobs = None
        choices = None

        # Helper: accept only plain dict/list structures; ignore MagicMock-like objects
        def _as_dict(val):
            if isinstance(val, dict):
                return val
            try:
                if hasattr(val, "model_dump"):
                    dumped = val.model_dump()
                    if isinstance(dumped, dict):
                        return dumped
                if hasattr(val, "to_dict"):
                    dumped = val.to_dict()
                    if isinstance(dumped, dict):
                        return dumped
            except Exception:
                return None
            return None

        # Try to extract function_call from the explicit message payload first
        try:
            msg = getattr(choice, "message", None) if not isinstance(choice, dict) else choice.get("message")

            # 1) direct attribute on SDK object / MagicMock
            try:
                direct_fc = getattr(msg, "function_call", None)
                if isinstance(direct_fc, dict):
                    function_call = direct_fc
            except Exception:
                direct_fc = None

            # 2) dict-like message (e.g., model_dump) or convertible via _as_dict
            if function_call is None:
                msg_dict = _as_dict(msg) if msg is not None else None
                if isinstance(msg_dict, dict):
                    fc = msg_dict.get("function_call")
                    if isinstance(fc, dict):
                        function_call = fc
        except Exception:
            function_call = None

        # Extract logprobs from the choice only if it's a plain mapping
        try:
            if isinstance(choice, dict):
                lp = choice.get("logprobs")
                if isinstance(lp, dict):
                    logprobs = lp
            else:
                lp = getattr(choice, "logprobs", None)
                if isinstance(lp, dict):
                    logprobs = lp
        except Exception:
            logprobs = None

        # Convert raw choices to plain dicts where possible for downstream tooling/tests
        try:
            raw = None
            if hasattr(openai_response, "model_dump"):
                dumped = None
                try:
                    dumped = openai_response.model_dump()
                except Exception:
                    dumped = None
                if isinstance(dumped, dict):
                    raw = dumped
            elif isinstance(openai_response, dict):
                raw = openai_response

            if isinstance(raw, dict):
                raw_choices = raw.get("choices")
                if isinstance(raw_choices, list) and all(isinstance(c, dict) for c in raw_choices):
                    choices = raw_choices
        except Exception:
            choices = None

        # Estimate cost
        temp_response = ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=self._model,
            provider="openai",
        )
        cost = self.estimate_cost(temp_response)

        # Sanitize raw_response (only accept dicts)
        raw_response = {}
        if hasattr(openai_response, "model_dump"):
            try:
                dumped = openai_response.model_dump()
                if isinstance(dumped, dict):
                    raw_response = dumped
            except Exception:
                raw_response = {}
        elif isinstance(openai_response, dict):
            raw_response = openai_response

        return ModelResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_name=getattr(openai_response, 'model', openai_response.get('model') if isinstance(openai_response, dict) else None),
            provider="openai",
            finish_reason=(getattr(choice, 'finish_reason', None) if choice is not None else None),
            estimated_cost_usd=cost,
            raw_response=raw_response,
            choices=choices,
            function_call=function_call,
            logprobs=logprobs,
        )
    
    async def close(self):
        """Clean up the async client."""
        await self.client.close()
