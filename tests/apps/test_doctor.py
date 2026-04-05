from __future__ import annotations

from pathlib import Path

import apps.cli.doctor as doctor
from apps.cli.doctor import run_checks
from core.runtime.config import load_runtime_config


def _status_by_name(results):
    return {item.name: item.status for item in results}


def _message_by_name(results):
    return {item.name: item.message for item in results}


def test_doctor_reports_missing_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = load_runtime_config()
    cfg.llm.enabled = True
    cfg.llm.provider = "openai"
    results = run_checks(cfg, force_benchmark=False)
    statuses = _status_by_name(results)
    assert statuses.get("llm_credentials") == "FAIL"


def test_doctor_resolves_benchmark_paths_from_resource_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MHD_RESOURCE_ROOT", str(tmp_path))
    resolved = doctor._resolve_benchmark_resource_path("third_party/verilog-eval")
    assert resolved == (tmp_path / "third_party" / "verilog-eval").resolve()


def test_doctor_reports_missing_benchmark_framework(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("apps.cli.doctor._benchmark_broker_ready", lambda cfg: (True, "ok"))
    cfg = load_runtime_config()
    cfg.benchmark.verilog_eval_root = str(tmp_path / "missing_framework")
    cfg.benchmark.prompts_dir = str(tmp_path / "missing_prompts")
    results = run_checks(cfg, force_benchmark=True)
    statuses = _status_by_name(results)
    assert statuses.get("benchmark_framework") == "FAIL"
    assert statuses.get("benchmark_prompts") == "FAIL"


def test_doctor_reports_tool_config_path_missing(tmp_path: Path):
    cfg = load_runtime_config()
    cfg.tools.verilator_path = str(tmp_path / "missing_verilator")
    cfg.tools.iverilog_path = str(tmp_path / "missing_iverilog")
    cfg.tools.vvp_path = str(tmp_path / "missing_vvp")
    results = run_checks(cfg, force_benchmark=False)
    statuses = _status_by_name(results)
    assert statuses.get("tool_verilator") == "WARN"
    assert statuses.get("tool_iverilog") == "WARN"
    assert statuses.get("tool_vvp") == "WARN"


def test_doctor_reports_missing_benchmark_analyzer_deps(tmp_path: Path, monkeypatch):
    cfg = load_runtime_config()
    framework_root = tmp_path / "verilog_eval"
    (framework_root / "scripts").mkdir(parents=True)
    (framework_root / "scripts" / "sv-iv-analyze").write_text("#!/usr/bin/env bash\n")
    (framework_root / "Makefile.in").write_text("all:\n")
    (framework_root / "dataset_spec-to-rtl").mkdir()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "Prob001_zero_prompt.txt").write_text("prompt\n")
    (prompts_dir / "problems.txt").write_text("Prob001_zero\n")

    cfg.benchmark.verilog_eval_root = str(framework_root)
    cfg.benchmark.prompts_dir = str(prompts_dir)
    cfg.tools.verilator_path = "true"
    cfg.tools.iverilog_path = "true"
    cfg.tools.vvp_path = "true"
    monkeypatch.setattr("apps.cli.doctor._benchmark_broker_ready", lambda cfg: (True, "ok"))
    monkeypatch.setattr("apps.cli.doctor.importlib.util.find_spec", lambda name: None if name == "langchain.schema" else object())

    results = run_checks(cfg, force_benchmark=True)
    statuses = _status_by_name(results)
    messages = _message_by_name(results)
    assert "official *_prompt.txt" in messages.get("benchmark_prompts", "")
    assert statuses.get("benchmark_analyzer_deps") == "FAIL"
    assert statuses.get("benchmark_broker") == "PASS"
    assert statuses.get("benchmark_verilator") == "PASS"


def test_doctor_reports_missing_benchmark_broker(tmp_path: Path, monkeypatch):
    cfg = load_runtime_config()
    framework_root = tmp_path / "verilog_eval"
    (framework_root / "scripts").mkdir(parents=True)
    (framework_root / "scripts" / "sv-iv-analyze").write_text("#!/usr/bin/env bash\n")
    (framework_root / "Makefile.in").write_text("all:\n")
    (framework_root / "dataset_spec-to-rtl").mkdir()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "Prob001_zero_prompt.txt").write_text("prompt\n")

    cfg.benchmark.verilog_eval_root = str(framework_root)
    cfg.benchmark.prompts_dir = str(prompts_dir)
    cfg.tools.verilator_path = "true"
    cfg.tools.iverilog_path = "true"
    cfg.tools.vvp_path = "true"

    monkeypatch.setattr("apps.cli.doctor._benchmark_broker_ready", lambda cfg: (False, "no broker"))
    results = run_checks(cfg, force_benchmark=True)
    statuses = _status_by_name(results)
    assert statuses.get("benchmark_broker") == "FAIL"


def test_doctor_reports_missing_benchmark_verilator(tmp_path: Path, monkeypatch):
    cfg = load_runtime_config()
    framework_root = tmp_path / "verilog_eval"
    (framework_root / "scripts").mkdir(parents=True)
    (framework_root / "scripts" / "sv-iv-analyze").write_text("#!/usr/bin/env bash\n")
    (framework_root / "Makefile.in").write_text("all:\n")
    (framework_root / "dataset_spec-to-rtl").mkdir()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "Prob001_zero_prompt.txt").write_text("prompt\n")

    cfg.benchmark.verilog_eval_root = str(framework_root)
    cfg.benchmark.prompts_dir = str(prompts_dir)
    cfg.tools.verilator_path = str(tmp_path / "missing_verilator")
    cfg.tools.iverilog_path = "true"
    cfg.tools.vvp_path = "true"

    monkeypatch.setattr("apps.cli.doctor._benchmark_broker_ready", lambda cfg: (True, "ok"))
    results = run_checks(cfg, force_benchmark=True)
    statuses = _status_by_name(results)
    assert statuses.get("benchmark_verilator") == "FAIL"


def test_doctor_warns_when_openai_rag_key_missing_but_fail_open(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("apps.cli.doctor._has_module", lambda name: True)
    cfg = load_runtime_config()
    cfg.rag.enabled = True
    cfg.rag.fail_open = True
    results = run_checks(cfg, force_benchmark=False)
    statuses = _status_by_name(results)
    assert statuses.get("rag_credentials") == "WARN"


def test_doctor_reports_rag_benchmark_policy(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("apps.cli.doctor._has_module", lambda name: True)
    monkeypatch.setattr("apps.cli.doctor.resolve_resource_path", lambda path: Path(__file__).resolve())
    cfg = load_runtime_config()
    cfg.rag.enabled = True
    cfg.rag.allow_benchmark = False
    results = run_checks(cfg, force_benchmark=True)
    statuses = _status_by_name(results)
    assert statuses.get("rag_benchmark_policy") == "WARN"


def test_doctor_reports_benchmark_rag_disabled_as_expected_default():
    cfg = load_runtime_config(Path("config/runtime.benchmark.yaml"))
    results = run_checks(cfg, force_benchmark=True)
    statuses = _status_by_name(results)
    messages = _message_by_name(results)
    assert statuses.get("rag_enabled") == "PASS"
    assert messages.get("rag_enabled") == "RAG disabled for benchmark runs by default."
