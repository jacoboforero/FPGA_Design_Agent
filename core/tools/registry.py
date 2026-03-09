"""
Tool registry — loads tool_registry.yaml once and provides resolved tool
configs to workers. Resolution order: env var → YAML path → shutil.which.
"""
from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandSpec:
    template: str
    timeout_seconds: int = 30

    def build(self, **kwargs: Any) -> list[str]:
        """Render the template and parse it into an argv list."""
        rendered = self.template.format(**kwargs)
        return shlex.split(rendered)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    resolved_path: str                          # absolute path to the binary
    commands: dict[str, CommandSpec]
    capabilities: dict[str, Any] = field(default_factory=dict)

    def cmd(self, command_name: str) -> CommandSpec:
        try:
            return self.commands[command_name]
        except KeyError:
            raise KeyError(f"Tool '{self.name}' has no command '{command_name}'") from None

    def can(self, flag: str) -> Any:
        return self.capabilities.get(flag, False)


@dataclass(frozen=True)
class SimulationConfig:
    artifact_base: str
    waveform_filename: str
    fail_window_before: int
    fail_window_after: int


@dataclass(frozen=True)
class LintConfig:
    # VERILATOR_STRICT_WARNINGS env var takes precedence over the YAML value.
    strict_warnings: bool


@dataclass(frozen=True)
class ToolRegistry:
    tools: dict[str, ToolSpec]
    simulation: SimulationConfig
    lint: LintConfig

    def get(self, name: str) -> ToolSpec:
        try:
            return self.tools[name]
        except KeyError:
            raise KeyError(f"No tool '{name}' in registry") from None

    def resolved_path(self, name: str) -> str:
        return self.get(name).resolved_path


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _resolve_binary(tool_name: str, raw: dict) -> str:
    """Resolve a tool binary using env var → YAML path → shutil.which."""
    env_key = raw.get("env_override", "")
    if env_key and (env_val := os.getenv(env_key)):
        return env_val

    yaml_path = raw.get("path")
    if yaml_path and Path(yaml_path).is_file():
        return yaml_path

    system_name = raw.get("system_name", tool_name)
    found = shutil.which(system_name)
    if found:
        return found

    raise FileNotFoundError(
        f"Tool '{tool_name}' not found. "
        f"Set {env_key!r} env var, add 'path' to the registry, "
        f"or install '{system_name}' on PATH."
    )


def _load_commands(raw_commands: dict) -> dict[str, CommandSpec]:
    return {
        cmd_name: CommandSpec(
            template=spec["template"],
            timeout_seconds=int(spec.get("timeout_seconds", 30)),
        )
        for cmd_name, spec in (raw_commands or {}).items()
    }


def _load_tool(name: str, raw: dict) -> ToolSpec:
    return ToolSpec(
        name=name,
        resolved_path=_resolve_binary(name, raw),
        commands=_load_commands(raw.get("commands", {})),
        capabilities=raw.get("capabilities", {}),
    )


def _load_simulation_config(raw: dict, registry_yaml: dict) -> SimulationConfig:
    sim = registry_yaml.get("simulation", {})
    fw = sim.get("fail_window", {})
    return SimulationConfig(
        artifact_base=sim.get("artifact_base", "artifacts/task_memory"),
        waveform_filename=sim.get("waveform_filename", "waveform.vcd"),
        fail_window_before=int(os.getenv("SIM_FAIL_WINDOW_BEFORE", fw.get("before_cycles", 20))),
        fail_window_after=int(os.getenv("SIM_FAIL_WINDOW_AFTER", fw.get("after_cycles", 5))),
    )


def _load_lint_config(registry_yaml: dict) -> LintConfig:
    lint = registry_yaml.get("lint", {})
    # Env var is the override; fall back to the YAML boolean, then False.
    env_val = os.getenv("VERILATOR_STRICT_WARNINGS")
    if env_val is not None:
        strict = env_val.strip() == "1"
    else:
        strict = bool(lint.get("strict_warnings", False))
    return LintConfig(strict_warnings=strict)


def load_registry(yaml_path: str | Path = "tool_registry.yaml") -> ToolRegistry:
    """Parse the YAML file and return a fully resolved ToolRegistry."""
    with open(yaml_path) as fh:
        raw = yaml.safe_load(fh)

    tools = {
        name: _load_tool(name, spec)
        for name, spec in raw.get("tools", {}).items()
    }
    return ToolRegistry(
        tools=tools,
        simulation=_load_simulation_config({}, raw),
        lint=_load_lint_config(raw),
    )


@lru_cache(maxsize=1)
def get_registry(yaml_path: str = "tool_registry.yaml") -> ToolRegistry:
    """Singleton accessor — loads once per process."""
    return load_registry(yaml_path)
