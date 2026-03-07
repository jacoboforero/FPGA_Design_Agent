"""
Qwen local implementation of the LLM Gateway interface.

Handles local Qwen model calls through Ollama. This general adapter
supports selecting the variant model (for example `qwen3:4b`) via the
`model` constructor argument or the `DEFAULT_LLM_MODEL` environment variable
passed by the factory.
"""

from typing import Optional, List
import logging
import httpx
from adapters.llm.gateway import (
	LLMGateway,
	Message,
	ModelResponse,
	GenerationConfig,
)

logger = logging.getLogger(__name__)


class QwenLocalGateway(LLMGateway):
	"""
	Gateway implementation for local Qwen models running via Ollama.

	The adapter accepts a `model` parameter which defaults to `qwen3:4b`.
	"""

	def __init__(
		self,
		model: str = "qwen3:4b",
		ollama_base_url: str = "http://localhost:11434",
		timeout: float = 300.0,
	):
		self._model = model
		self._base_url = ollama_base_url.rstrip("/")
		self._api_url = f"{self._base_url}/api/chat"
		self._timeout = timeout
		self.logger = logger

	async def generate(
		self,
		messages: List[Message],
		config: Optional[GenerationConfig] = None,
	) -> ModelResponse:
		config = config or GenerationConfig()
		config = self.validate_config(config)

		ollama_messages = self._convert_messages(messages)

		request_data = {
			"model": self._model,
			"messages": ollama_messages,
			"stream": False,
		}

		options = {}
		if config.temperature is not None:
			options["temperature"] = config.temperature
		if config.top_p is not None:
			options["top_p"] = config.top_p
		if config.top_k is not None:
			options["top_k"] = config.top_k
		if config.stop_sequences:
			options["stop"] = config.stop_sequences
		if config.max_tokens is not None:
			options["num_predict"] = config.max_tokens

		if getattr(config, "functions", None) is not None:
			options["functions"] = config.functions
		if getattr(config, "function_call", None) is not None:
			options["function_call"] = config.function_call
		if getattr(config, "n", None) is not None:
			options["n"] = config.n

		lp = getattr(config, "logprobs", None)
		if lp is not None:
			try:
				lp_int = int(lp)
				if lp_int > 0:
					options["logprobs"] = True
					options["top_logprobs"] = lp_int
				else:
					options["logprobs"] = False
			except Exception:
				options["logprobs"] = lp

		if getattr(config, "user", None) is not None:
			options["user"] = config.user
		if getattr(config, "stream", None) is not None:
			options["stream"] = config.stream

		provider_specific = dict(config.provider_specific or {})

		for key in [
			"presence_penalty",
			"seed",
			"response_format",
			"modalities",
			"audio",
			"enable_code_interpreter",
			"enable_thinking",
			"thinking_budget",
			"stream_options",
			"enable_search",
			"search_options",
			"tool_choice",
			"tools",
			"parallel_tool_calls",
			"top_logprobs",
			"top_k",
		]:
			if key in provider_specific and key not in options:
				options[key] = provider_specific[key]

		for k, v in provider_specific.items():
			if k not in options:
				options[k] = v

		if options:
			request_data["options"] = options

		try:
			async with httpx.AsyncClient(timeout=self._timeout) as client:
				response = await client.post(self._api_url, json=request_data)
				response.raise_for_status()
				ollama_response = response.json()

			model_response = self._convert_response(ollama_response)
			return model_response

		except httpx.TimeoutException as e:
			raise RuntimeError(
				f"Qwen request timed out after {self._timeout}s. Error: {e}"
			)
		except httpx.HTTPStatusError as e:
			raise RuntimeError(f"Qwen HTTP error {e.response.status_code}: {e.response.text}")
		except httpx.ConnectError as e:
			raise RuntimeError(f"Cannot connect to Ollama at {self._base_url}. Is Ollama running? Error: {e}")
		except Exception as e:
			raise RuntimeError(f"Qwen API error: {e}")

	@property
	def model_name(self) -> str:
		return self._model

	@property
	def provider(self) -> str:
		return "qwen-local"

	@property
	def supports_files(self) -> bool:
		return True

	def validate_config(self, config: GenerationConfig) -> GenerationConfig:
		if config.temperature is not None:
			if not 0 <= config.temperature <= 2:
				raise ValueError("Qwen temperature must be in [0, 2]")

		if config.top_p is not None:
			if not 0 <= config.top_p <= 1:
				raise ValueError("Qwen top_p must be in [0, 1]")

		if config.top_k is not None:
			if config.top_k < 1:
				raise ValueError("Qwen top_k must be >= 1")

		if config.max_tokens is not None:
			if config.max_tokens > 32000:
				self.logger.warning(
					f"max_tokens={config.max_tokens} exceeds recommended 32K limit for Qwen"
				)

		ps = config.provider_specific or {}
		if "presence_penalty" in ps:
			pp = float(ps["presence_penalty"])
			if not -2.0 <= pp <= 2.0:
				raise ValueError("Qwen presence_penalty must be in [-2.0, 2.0]")

		if "seed" in ps:
			s = int(ps["seed"])
			if not (0 <= s <= 2 ** 31 - 1):
				raise ValueError("Qwen seed must be in [0, 2**31-1]")

		if "thinking_budget" in ps:
			tb = int(ps["thinking_budget"])
			if tb < 0:
				raise ValueError("Qwen thinking_budget must be >= 0")

		if "top_logprobs" in ps:
			tl = int(ps["top_logprobs"])
			if not 0 <= tl <= 5:
				raise ValueError("Qwen top_logprobs must be in [0,5]")

		return config

	def estimate_cost(self, response: ModelResponse) -> float:
		return 0.0

	def _convert_messages(self, messages: List[Message]) -> List[dict]:
		ollama_messages = []

		for msg in messages:
			ollama_msg = {"role": msg.role.value, "content": msg.content}

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
					ollama_msg["content"] = msg.content + "".join(file_contents)

			ollama_messages.append(ollama_msg)

		return ollama_messages

	def _convert_response(self, ollama_response: dict) -> ModelResponse:
		message = ollama_response.get("message", {})
		content = message.get("content", "")

		prompt_tokens = ollama_response.get("prompt_eval_count", 0)
		completion_tokens = ollama_response.get("eval_count", 0)
		total_tokens = prompt_tokens + completion_tokens

		if prompt_tokens == 0 and completion_tokens == 0:
			self.logger.warning(
				"Ollama did not return token counts. Cost tracking may be inaccurate."
			)

		finish_reason = ollama_response.get("done_reason", "stop")

		function_call = ollama_response.get("function_call") or ollama_response.get("tool_call")
		choices = ollama_response.get("choices")

		return ModelResponse(
			content=content,
			input_tokens=prompt_tokens,
			output_tokens=completion_tokens,
			total_tokens=total_tokens,
			estimated_cost_usd=0.0,
			model_name=self._model,
			provider="qwen-local",
			finish_reason=finish_reason,
			raw_response=ollama_response,
			choices=choices,
			function_call=function_call,
		)

	async def close(self):
		pass
