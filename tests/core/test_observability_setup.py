from __future__ import annotations

from types import SimpleNamespace

import core.observability.setup as setup_mod


def test_configure_observability_skips_agentops_when_disabled(monkeypatch):
    calls: list[tuple[str, object]] = []

    class _Tracker:
        run_name = "initial"
        run_id = "run-0"

        def init_from_env(self, **kwargs):
            calls.append(("init_from_env", kwargs))

        def disable(self, **kwargs):
            self.run_name = kwargs.get("run_name") or self.run_name
            self.run_id = kwargs.get("run_id") or self.run_id
            calls.append(("disable", kwargs))

    class _JsonlSink:
        def __init__(self, run_name: str, run_id: str, base_dir=None):
            self.run_name = run_name
            self.run_id = run_id

    tracker = _Tracker()
    monkeypatch.setattr(setup_mod, "get_tracker", lambda: tracker)
    monkeypatch.setattr(setup_mod, "JsonlFileSink", _JsonlSink)
    monkeypatch.setattr(
        setup_mod,
        "get_runtime_config",
        lambda: SimpleNamespace(observability=SimpleNamespace(agentops_enabled=False)),
    )
    monkeypatch.setattr(setup_mod, "set_global_sinks", lambda sinks: calls.append(("set_global_sinks", list(sinks))))

    setup_mod.configure_observability(run_name="demo", run_id="run-1", default_tags=["x"])

    assert ("disable", {"run_name": "demo", "run_id": "run-1"}) in calls
    assert not any(name == "init_from_env" for name, _ in calls)
    sink_call = next(payload for name, payload in calls if name == "set_global_sinks")
    assert len(sink_call) == 1
    assert isinstance(sink_call[0], _JsonlSink)
    assert sink_call[0].run_name == "demo"
    assert sink_call[0].run_id == "run-1"


def test_configure_observability_initializes_agentops_when_enabled(monkeypatch):
    calls: list[tuple[str, object]] = []

    class _Tracker:
        run_name = "initial"
        run_id = "run-0"

        def init_from_env(self, **kwargs):
            self.run_name = kwargs.get("run_name") or self.run_name
            self.run_id = kwargs.get("run_id") or self.run_id
            calls.append(("init_from_env", kwargs))

        def disable(self, **kwargs):
            calls.append(("disable", kwargs))

    class _JsonlSink:
        def __init__(self, run_name: str, run_id: str, base_dir=None):
            self.run_name = run_name
            self.run_id = run_id

    class _AgentOpsSink:
        def __init__(self, tracker):
            self.tracker = tracker

    tracker = _Tracker()
    monkeypatch.setattr(setup_mod, "get_tracker", lambda: tracker)
    monkeypatch.setattr(setup_mod, "JsonlFileSink", _JsonlSink)
    monkeypatch.setattr(setup_mod, "AgentOpsSink", _AgentOpsSink)
    monkeypatch.setattr(
        setup_mod,
        "get_runtime_config",
        lambda: SimpleNamespace(observability=SimpleNamespace(agentops_enabled=True)),
    )
    monkeypatch.setattr(setup_mod, "set_global_sinks", lambda sinks: calls.append(("set_global_sinks", list(sinks))))

    setup_mod.configure_observability(run_name="demo", run_id="run-1", default_tags=["x"])

    init_call = next(payload for name, payload in calls if name == "init_from_env")
    assert init_call["run_name"] == "demo"
    assert init_call["run_id"] == "run-1"
    sink_call = next(payload for name, payload in calls if name == "set_global_sinks")
    assert len(sink_call) == 2
    assert isinstance(sink_call[0], _AgentOpsSink)
    assert isinstance(sink_call[1], _JsonlSink)
