from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from agentops.semconv import AgentAttributes, SpanAttributes, SpanKind

import core.observability.agentops_tracker as tracker_mod
from adapters.observability.agentops import AgentOpsSink
from core.observability.events import Event


def test_record_runtime_event_maps_worker_events_to_agent_spans(monkeypatch):
    tracker = tracker_mod.AgentOpsTracker()
    tracker.enabled = True
    recorded: dict = {}
    monkeypatch.setattr(tracker, "_record_span", lambda **kwargs: recorded.update(kwargs))

    tracker.record_runtime_event(
        "worker_sim",
        "task_received",
        {"task_type": "SimWorker", "task_id": "task-1", "node_id": "top", "run_id": "run-1"},
    )

    assert recorded["operation_name"] == "worker_sim.task_received"
    assert recorded["span_kind"] == SpanKind.AGENT
    assert recorded["attributes"][AgentAttributes.AGENT_NAME] == "SimWorker"
    assert recorded["attributes"]["mhd.task_id"] == "task-1"
    assert recorded["attributes"]["mhd.node_id"] == "top"


def test_log_llm_call_records_manual_llm_spans(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker_mod, "ARTIFACTS_DIR", tmp_path)
    tracker = tracker_mod.AgentOpsTracker()
    tracker.enabled = True
    tracker.run_id = "run-1"
    recorded: dict = {}
    monkeypatch.setattr(tracker, "_record_span", lambda **kwargs: recorded.update(kwargs))

    tracker.log_llm_call(
        agent="implementation_agent",
        node_id="top",
        model="gpt-5",
        provider="openai",
        prompt_tokens=11,
        completion_tokens=9,
        total_tokens=20,
        estimated_cost_usd=0.125,
        metadata={"stage": "implementation"},
    )

    assert recorded["operation_name"] == "implementation_agent.implementation"
    assert recorded["span_kind"] == SpanKind.LLM
    assert recorded["attributes"][AgentAttributes.AGENT_NAME] == "implementation_agent"
    assert recorded["attributes"][SpanAttributes.LLM_REQUEST_MODEL] == "gpt-5"
    assert recorded["attributes"][SpanAttributes.LLM_USAGE_TOTAL_TOKENS] == 20
    assert recorded["attributes"]["mhd.node_id"] == "top"


def test_agentops_sink_forwards_events_for_metadata_and_spans():
    calls: list[tuple] = []

    class _Tracker:
        def log_event(self, event_type: str, payload: dict) -> None:
            calls.append(("log_event", event_type, payload))

        def record_runtime_event(self, runtime: str, event_type: str, payload: dict) -> None:
            calls.append(("record_runtime_event", runtime, event_type, payload))

    sink = AgentOpsSink(_Tracker())
    event = Event(
        runtime="orchestrator",
        event_type="task_published",
        payload={"task_id": "task-1"},
        timestamp=datetime.now(timezone.utc),
    )

    sink.send(event)

    assert calls == [
        ("log_event", "task_published", {"task_id": "task-1"}),
        ("record_runtime_event", "orchestrator", "task_published", {"task_id": "task-1"}),
    ]


def test_init_disables_agentops_openai_auto_instrumentation_when_beta_chat_missing(monkeypatch):
    class _FakeAgentOps:
        def __init__(self):
            self.init_kwargs = None

        def init(self, **kwargs):
            self.init_kwargs = kwargs

        def start_trace(self, trace_name, tags):
            return {"trace_name": trace_name, "tags": tags}

        def update_trace_metadata(self, payload):
            return payload

    fake_agentops = _FakeAgentOps()
    monkeypatch.setattr(tracker_mod, "agentops", fake_agentops)
    monkeypatch.setattr(tracker_mod, "get_runtime_config", lambda: SimpleNamespace(llm=SimpleNamespace(provider="openai", default_model="gpt-4.1-mini")))
    monkeypatch.setattr(tracker_mod.importlib.util, "find_spec", lambda name: None if name == "openai.resources.beta.chat" else object())
    monkeypatch.setenv("AGENTOPS_API_KEY", "test-key")

    tracker = tracker_mod.AgentOpsTracker()
    tracker.init_from_env(run_name="demo")

    assert tracker.enabled is True
    assert fake_agentops.init_kwargs is not None
    assert fake_agentops.init_kwargs["instrument_llm_calls"] is False
