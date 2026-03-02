from __future__ import annotations

from core.runtime.config import get_runtime_config, set_runtime_config
from core.runtime.llm_rate_control import LlmRateController


def test_llm_rate_control_backs_off_on_rate_limit_error():
    cfg = get_runtime_config().model_copy(deep=True)
    cfg.llm.rate_control.adaptive_enabled = True
    cfg.llm.rate_control.max_in_flight_min = 1
    cfg.llm.rate_control.max_in_flight_default = 4
    cfg.llm.rate_control.max_in_flight_max = 8
    cfg.llm.rate_control.backoff_on_429 = True
    set_runtime_config(cfg)

    controller = LlmRateController()
    assert controller._max_current == 4  # noqa: SLF001
    ticket = controller.acquire()
    controller.release(ticket, error=RuntimeError("429 rate limit exceeded"))
    assert controller._max_current == 3  # noqa: SLF001


def test_llm_rate_control_recovers_after_success_streak():
    cfg = get_runtime_config().model_copy(deep=True)
    cfg.llm.rate_control.adaptive_enabled = True
    cfg.llm.rate_control.max_in_flight_min = 1
    cfg.llm.rate_control.max_in_flight_default = 2
    cfg.llm.rate_control.max_in_flight_max = 3
    set_runtime_config(cfg)

    controller = LlmRateController()
    for _ in range(16):
        ticket = controller.acquire()
        controller.release(ticket, error=None)
    assert controller._max_current >= 3  # noqa: SLF001

