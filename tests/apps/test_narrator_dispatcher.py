from __future__ import annotations

from apps.cli.execution_narrator import NarratorDispatcher


class _StubNarrator:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def handle_event(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, dict(payload)))


def test_narrator_dispatcher_strict_mode_preserves_sequence():
    narrator = _StubNarrator()
    dispatcher = NarratorDispatcher(
        narrator,
        async_enabled=True,
        order_mode="strict",
        queue_max_events=64,
    )
    for idx in range(40):
        dispatcher.emit("stage_result", {"idx": idx, "status": "SUCCESS"})
    dispatcher.close()

    observed = [payload["idx"] for event_type, payload in narrator.events if event_type == "stage_result"]
    assert observed == list(range(40))


def test_narrator_dispatcher_sync_mode_is_immediate():
    narrator = _StubNarrator()
    dispatcher = NarratorDispatcher(
        narrator,
        async_enabled=False,
        order_mode="strict",
        queue_max_events=4,
    )
    dispatcher.emit("state_transition", {"state": "IMPLEMENTING"})
    dispatcher.emit("state_transition", {"state": "LINTING"})
    dispatcher.close()
    assert [payload["state"] for _, payload in narrator.events] == ["IMPLEMENTING", "LINTING"]

