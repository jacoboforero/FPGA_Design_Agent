"""
Runtime configuration loader and typed settings.

Runtime behavior is configured through YAML manifests with explicit domain
ownership. The public YAML shape is:

- run
- agents
- cli
- infrastructure
- verification
- benchmark

Internally, the loaded RuntimeConfig still exposes broker/workers/llm/tools/
lint/sim/debug sections to minimize churn in the rest of the codebase.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError

from core.runtime.paths import default_config_path


DEFAULT_CONFIG_PATH = default_config_path()

SpecInteraction = Literal["interactive", "non_interactive"]
RigorLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]
VerificationProfile = Literal["testbench-agent", "verilog-eval"]


class SpecProfileConfig(BaseModel):
    interaction: SpecInteraction = "interactive"
    rigor_level: RigorLevel = "L2"


class RunConfig(BaseModel):
    spec_profile: SpecProfileConfig = Field(default_factory=SpecProfileConfig)
    verification_profile: VerificationProfile = "testbench-agent"


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
    planner: int = 1
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
    flow_mode: Literal["orchestrated", "legacy_lightweight", "direct_single_module"] = "direct_single_module"
    prompt_mode: Literal["normalized", "raw_verilog_eval"] = "raw_verilog_eval"
    disable_tb_generation: bool = True
    debug_rtl_only: bool = True
    use_public_testbench: bool = True
    interface_equivalence: Literal["strict", "canonical_width"] = "canonical_width"
    rtl_language: Literal["verilog2001", "systemverilog"] = "systemverilog"
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


class RuntimeConfig(BaseModel):
    run: RunConfig = Field(default_factory=RunConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    cli: CliConfig = Field(default_factory=CliConfig)
    workers: WorkersConfig = Field(default_factory=WorkersConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    lint: LintConfig = Field(default_factory=LintConfig)
    sim: SimConfig = Field(default_factory=SimConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    benchmark: BenchmarkConfig = Field(default_factory=BenchmarkConfig)


def _default_runtime_dict() -> Dict[str, Any]:
    return {
        "run": {},
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


def _load_yaml_mapping(path: Path, *, seen: set[Path] | None = None) -> Dict[str, Any]:
    resolved = path.resolve()
    seen = seen or set()
    if resolved in seen:
        raise ValueError(f"Config include cycle detected at '{resolved}'.")
    if not resolved.exists():
        raise FileNotFoundError(f"Config file not found: {resolved}")
    raw = yaml.safe_load(resolved.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file '{resolved}' must contain a YAML mapping.")

    includes_raw = raw.pop("includes", [])
    if includes_raw is None:
        includes_raw = []
    if not isinstance(includes_raw, list):
        raise ValueError(f"Config file '{resolved}' has non-list 'includes'.")

    merged: Dict[str, Any] = {}
    next_seen = set(seen)
    next_seen.add(resolved)
    for item in includes_raw:
        include_name = str(item).strip()
        if not include_name:
            continue
        include_path = (resolved.parent / include_name).resolve()
        merged = _merge_dict(merged, _load_yaml_mapping(include_path, seen=next_seen))
    return _merge_dict(merged, raw)


def _flatten_agent_llm(agent_llm: Dict[str, Any]) -> Dict[str, Any]:
    defaults = agent_llm.get("defaults") if isinstance(agent_llm.get("defaults"), dict) else {}
    rate_control = agent_llm.get("rate_control") if isinstance(agent_llm.get("rate_control"), dict) else {}
    roles = agent_llm.get("roles") if isinstance(agent_llm.get("roles"), dict) else {}

    llm: Dict[str, Any] = {
        "enabled": agent_llm.get("enabled", True),
        "provider": agent_llm.get("provider", defaults.get("provider", "openai")),
        "default_model": defaults.get("model", "gpt-4.1-mini"),
        "request_timeout_s": defaults.get("request_timeout_s", 120.0),
        "json_mode": defaults.get("json_mode", True),
        "max_tokens": defaults.get("max_tokens", 10000),
        "temperature": defaults.get("temperature", 0.2),
        "top_p": defaults.get("top_p"),
        "rate_control": rate_control,
        "agent_overrides": {},
    }

    for role_name, raw_role in roles.items():
        if not isinstance(raw_role, dict):
            continue
        provider = raw_role.get("provider")
        model = raw_role.get("model")
        if provider or model:
            llm["agent_overrides"][str(role_name)] = {"provider": provider, "model": model}

    spec_helper = roles.get("spec_helper") if isinstance(roles.get("spec_helper"), dict) else {}
    phases = spec_helper.get("phases") if isinstance(spec_helper.get("phases"), dict) else {}
    extract = phases.get("extract") if isinstance(phases.get("extract"), dict) else {}
    question = phases.get("question") if isinstance(phases.get("question"), dict) else {}
    draft = phases.get("draft") if isinstance(phases.get("draft"), dict) else {}
    if spec_helper.get("model") is not None:
        llm["spec_helper_model"] = spec_helper.get("model")
    llm["max_tokens_spec"] = extract.get("max_tokens", llm["max_tokens"])
    llm["temperature_spec"] = extract.get("temperature", llm["temperature"])
    llm["max_tokens_spec_question"] = question.get("max_tokens", llm["max_tokens_spec_question"] if "max_tokens_spec_question" in llm else 1500)
    llm["temperature_spec_question"] = question.get("temperature", 0.3)
    llm["max_tokens_spec_draft"] = draft.get("max_tokens", llm["max_tokens_spec_draft"] if "max_tokens_spec_draft" in llm else 2500)
    llm["temperature_spec_draft"] = draft.get("temperature", 0.4)

    reflection = roles.get("reflection") if isinstance(roles.get("reflection"), dict) else {}
    llm["max_tokens_reflect"] = reflection.get("max_tokens", 6000)
    llm["temperature_reflect"] = reflection.get("temperature", 0.2)

    debug = roles.get("debug") if isinstance(roles.get("debug"), dict) else {}
    llm["max_tokens_debug"] = debug.get("max_tokens", 7000)
    llm["temperature_debug"] = debug.get("temperature", 0.2)

    narrator = roles.get("narrator") if isinstance(roles.get("narrator"), dict) else {}
    llm["narrative_model"] = narrator.get("model")
    llm["narrative_fallback_model"] = narrator.get("fallback_model", "gpt-4.1-mini")
    llm["narrative_max_tokens"] = narrator.get("max_tokens", 220)
    llm["narrative_temperature"] = narrator.get("temperature", 0.5)
    llm["narrative_timeout_s"] = narrator.get("timeout_s", 10.0)

    return llm


def _normalize_runtime_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(raw)

    agents = normalized.pop("agents", None)
    if isinstance(agents, dict):
        pools = agents.get("pools")
        if isinstance(pools, dict):
            normalized["workers"] = _merge_dict(normalized.get("workers", {}), {"pool_sizes": pools})
        agent_llm = agents.get("llm")
        if isinstance(agent_llm, dict):
            normalized["llm"] = _merge_dict(normalized.get("llm", {}), _flatten_agent_llm(agent_llm))

    infrastructure = normalized.pop("infrastructure", None)
    if isinstance(infrastructure, dict):
        broker = infrastructure.get("broker")
        if isinstance(broker, dict):
            normalized["broker"] = _merge_dict(normalized.get("broker", {}), broker)
        tool_paths = infrastructure.get("tool_paths")
        if isinstance(tool_paths, dict):
            normalized["tools"] = _merge_dict(
                normalized.get("tools", {}),
                {
                    "verilator_path": tool_paths.get("verilator"),
                    "iverilog_path": tool_paths.get("iverilog"),
                    "vvp_path": tool_paths.get("vvp"),
                },
            )

    verification = normalized.pop("verification", None)
    if isinstance(verification, dict):
        lint = verification.get("lint")
        if isinstance(lint, dict):
            normalized["lint"] = _merge_dict(normalized.get("lint", {}), lint)
        sim = verification.get("sim")
        if isinstance(sim, dict):
            normalized["sim"] = _merge_dict(normalized.get("sim", {}), sim)
        debug = verification.get("debug")
        if isinstance(debug, dict):
            normalized["debug"] = _merge_dict(normalized.get("debug", {}), debug)

    return normalized


def load_runtime_config(path: Optional[Path] = None) -> RuntimeConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    merged = _default_runtime_dict()
    if cfg_path.exists():
        raw = _load_yaml_mapping(cfg_path)
        merged = _merge_dict(merged, _normalize_runtime_shape(raw))
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


def initialize_runtime_config(path: Optional[Path] = None) -> RuntimeConfig:
    config = load_runtime_config(path)
    set_runtime_config(config)
    return config


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "SpecProfileConfig",
    "RunConfig",
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
    "RuntimeConfig",
    "load_runtime_config",
    "set_runtime_config",
    "get_runtime_config",
    "initialize_runtime_config",
]
