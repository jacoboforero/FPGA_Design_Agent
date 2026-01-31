from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FakeResponse:
    content: str
    provider: str = "fake"
    model_name: str = "fake-model"
    input_tokens: int = 10
    output_tokens: int = 10
    total_tokens: int = 20
    estimated_cost_usd: float = 0.0


class FakeGateway:
    def __init__(self, response: FakeResponse):
        self.response = response

    async def generate(self, messages, config):
        return self.response
