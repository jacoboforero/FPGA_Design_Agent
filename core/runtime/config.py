"""
Runtime configuration loader and typed settings.

Behavior is configured via YAML presets. Environment variables are reserved for
secrets/credentials and compatibility fallbacks.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError


DEFAULT_CONFIG_PATH = Path("config/runtime.yaml")


class BrokerConfig(BaseModel):
    url: str = "amqp://user:password@localhost:5672/"
    heartbeat: int = 600
    blocked_connection_timeout: float = 300.0
    connection_attempts: int = 5
    retry_delay: float = 2.0
    socket_timeout: float = 10.0
    reconnect_delay_s: float = 1.0
    task_max_retries: int = 1
    purge_queues_on_start: bool = True
    planner_timeout_s: float = 60.0
    results_consume_mode: str = "consume"


class CliConfig(BaseModel):
    default_narrative_mode: str = "llm"
    narrative_show_state: bool = False
    execution_narrator_async: bool = True
    execution_narrator_order_mode: str = "strict"
    execution_narrator_queue_max_events: int = 256


class WorkerPoolSizesConfig(BaseModel):
    implementation: int = 1
    testbench: int = 1
    reflection: int = 1
    debug: int = 1
    spec_helper: int = 1
    lint: int = 1
    tb_lint: int = 1
    acceptance: int = 1
    distill: int = 1
    simulation: int = 1


class WorkersConfig(BaseModel):
    pool_sizes: WorkerPoolSizesConfig = Field(default_factory=WorkerPoolSizesConfig)


class LlmRateControlConfig(BaseModel):
    adaptive_enabled: bool = True
    max_in_flight_min: int = 1
    max_in_flight_default: int = 4
    max_in_flight_max: int = 8
    backoff_on_429: bool = True


class LlmAgentOverrideConfig(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


class LlmConfig(BaseModel):
    enabled: bool = True
    provider: str = "openai"
    default_model: str = "gpt-4.1-mini"
    request_timeout_s: float = 120.0
    agent_overrides: Dict[str, LlmAgentOverrideConfig] = Field(default_factory=dict)
    spec_helper_model: Optional[str] = None
    narrative_model: Optional[str] = None
    narrative_fallback_model: str = "gpt-4.1-mini"
    json_mode: bool = True
    max_tokens: int = 10000
    temperature: float = 0.2
    top_p: Optional[float] = None
    max_tokens_spec: int = 4000
    temperature_spec: float = 0.2
    max_tokens_spec_question: int = 1500
    temperature_spec_question: float = 0.3
    max_tokens_spec_draft: int = 2500
    temperature_spec_draft: float = 0.4
    max_tokens_reflect: int = 6000
    temperature_reflect: float = 0.2
    max_tokens_debug: int = 7000
    temperature_debug: float = 0.2
    narrative_temperature: float = 0.5
    narrative_max_tokens: int = 220
    narrative_timeout_s: float = 10.0
    rate_control: LlmRateControlConfig = Field(default_factory=LlmRateControlConfig)


class ToolConfig(BaseModel):
    verilator_path: Optional[str] = None
    iverilog_path: Optional[str] = None
    vvp_path: Optional[str] = None


class LintConfig(BaseModel):
    verilator_strict_warnings: bool = False
    rtl_fail_moddup: bool = True
    rtl_semantic_enabled: bool = True
    rtl_semantic_strict: bool = True
    tb_semantic_enabled: bool = True
    tb_semantic_strict: bool = True


class SimConfig(BaseModel):
    fail_window_before: int = 20
    fail_window_after: int = 5
    vcd_max_signals: int = 40
    vcd_max_changes_per_signal: int = 200
    vcd_time_window_before: int = 2000
    vcd_time_window_after: int = 2000


class DebugConfig(BaseModel):
    max_retries: int = 2
    max_attempts: int = 3
    local_lint_timeout_s: float = 12.0
    local_lint_max_lines: int = 20


class BenchmarkSampleConfig(BaseModel):
    n: int
    temperature: float
    top_p: float


class BenchmarkConfig(BaseModel):
    verilog_eval_root: str = "third_party/verilog-eval"
    prompts_dir: str = "third_party/verilog-eval/dataset_spec-to-rtl"
    output_root: str = "artifacts/benchmarks/verilog_eval"
    oracle_manifest: Optional[str] = None
    sim_run_timeout_s: float = 90.0
    near_miss_extra_retry_enabled: bool = True
    near_miss_max_mismatches: int = 20
    near_miss_extra_debug_retries: int = 1
    canonical: BenchmarkSampleConfig = Field(
        default_factory=lambda: BenchmarkSampleConfig(n=1, temperature=0.0, top_p=0.01)
    )
    sampled: BenchmarkSampleConfig = Field(
        default_factory=lambda: BenchmarkSampleConfig(n=20, temperature=0.8, top_p=0.95)
    )


class PresetConfig(BaseModel):
    spec_profile: str
    verification_profile: str
    allow_repair_loop: bool = True
    interactive_spec_helper: bool = True
    benchmark_mode: bool = False


class RuntimeConfig(BaseModel):
    active_preset: str = "engineer_fast"
    presets: Dict[str, PresetConfig] = Field(default_factory=dict)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    cli: CliConfig = Field(default_factory=CliConfig)
    workers: WorkersConfig = Field(default_factory=WorkersConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    lint: LintConfig = Field(default_factory=LintConfig)
    sim: SimConfig = Field(default_factory=SimConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    benchmark: BenchmarkConfig = Field(default_factory=BenchmarkConfig)

    def get_preset(self, name: Optional[str] = None) -> PresetConfig:
        key = name or self.active_preset
        if key not in self.presets:
            raise KeyError(f"Unknown preset '{key}'. Available: {sorted(self.presets)}")
        return self.presets[key]

    @property
    def resolved_preset(self) -> PresetConfig:
        return self.get_preset(self.active_preset)


def _default_runtime_dict() -> Dict[str, Any]:
    return {
        "active_preset": "engineer_fast",
        "presets": {
            "engineer_fast": {
                "spec_profile": "engineer_fast",
                "verification_profile": "hybrid_scoreboard",
                "allow_repair_loop": True,
                "interactive_spec_helper": True,
                "benchmark_mode": False,
            },
            "engineer_signoff": {
                "spec_profile": "engineer_signoff",
                "verification_profile": "strict_tb_acceptance",
                "allow_repair_loop": True,
                "interactive_spec_helper": True,
                "benchmark_mode": False,
            },
            "benchmark": {
                "spec_profile": "benchmark",
                "verification_profile": "oracle_compare",
                "allow_repair_loop": True,
                "interactive_spec_helper": False,
                "benchmark_mode": True,
            },
        },
        "broker": {},
        "cli": {},
        "workers": {},
        "llm": {},
        "tools": {},
        "lint": {},
        "sim": {},
        "debug": {},
        "benchmark": {},
    }


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def load_runtime_config(path: Optional[Path] = None, *, preset_override: Optional[str] = None) -> RuntimeConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    merged = _default_runtime_dict()
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Config file '{cfg_path}' must contain a YAML mapping.")
        merged = _merge_dict(merged, raw)
    if preset_override:
        merged["active_preset"] = preset_override
    try:
        return RuntimeConfig.model_validate(merged)
    except ValidationError as exc:
        raise ValueError(f"Invalid runtime configuration in '{cfg_path}': {exc}") from exc


_RUNTIME_CONFIG: Optional[RuntimeConfig] = None


def set_runtime_config(config: RuntimeConfig) -> None:
    global _RUNTIME_CONFIG
    _RUNTIME_CONFIG = config


def get_runtime_config() -> RuntimeConfig:
    global _RUNTIME_CONFIG
    if _RUNTIME_CONFIG is None:
        _RUNTIME_CONFIG = load_runtime_config()
    return _RUNTIME_CONFIG


def initialize_runtime_config(path: Optional[Path] = None, *, preset_override: Optional[str] = None) -> RuntimeConfig:
    config = load_runtime_config(path, preset_override=preset_override)
    set_runtime_config(config)
    return config


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "BrokerConfig",
    "CliConfig",
    "WorkersConfig",
    "WorkerPoolSizesConfig",
    "LlmConfig",
    "LlmAgentOverrideConfig",
    "LlmRateControlConfig",
    "ToolConfig",
    "LintConfig",
    "SimConfig",
    "DebugConfig",
    "BenchmarkConfig",
    "BenchmarkSampleConfig",
    "PresetConfig",
    "RuntimeConfig",
    "load_runtime_config",
    "set_runtime_config",
    "get_runtime_config",
    "initialize_runtime_config",
]
