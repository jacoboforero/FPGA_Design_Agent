"""
Static tool registry.

The registry owns command templates and capability metadata only. Machine-
specific binary resolution lives in runtime config (`infrastructure.tool_paths`)
with `shutil.which(...)` as fallback.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from core.runtime.paths import default_tool_registry_path


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
    commands: dict[str, CommandSpec]
    capabilities: dict[str, Any] = field(default_factory=dict)
    resolved_path: str | None = None

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
        resolved_path=None,
        commands=_load_commands(raw.get("commands", {})),
        capabilities=raw.get("capabilities", {}),
    )


def _load_simulation_config(raw: dict, registry_yaml: dict) -> SimulationConfig:
    return SimulationConfig(
        artifact_base="artifacts/task_memory",
        waveform_filename="waveform.vcd",
        fail_window_before=20,
        fail_window_after=5,
    )


def _load_lint_config(registry_yaml: dict) -> LintConfig:
    return LintConfig(strict_warnings=False)


def load_registry(yaml_path: str | Path | None = None) -> ToolRegistry:
    """Parse the YAML file and return a fully resolved ToolRegistry."""
    yaml_path = Path(yaml_path) if yaml_path is not None else default_tool_registry_path()
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
def get_registry(yaml_path: str | None = None) -> ToolRegistry:
    """Singleton accessor — loads once per process."""
    return load_registry(yaml_path)
