from apps.cli import cli, doctor


def test_cli_prefers_explicit_rabbitmq_env(monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://override:secret@localhost:5672/")
    assert cli._resolve_broker_url("amqp://guest:guest@localhost:5672/") == "amqp://override:secret@localhost:5672/"


def test_doctor_prefers_explicit_rabbitmq_env(monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://override:secret@localhost:5672/")
    assert doctor._resolve_broker_url("amqp://guest:guest@localhost:5672/") == "amqp://override:secret@localhost:5672/"
