"""
Path helpers for developer and installed CLI environments.

The codebase historically assumed it was always run from the repository root.
For Homebrew-style installs we need to distinguish:

- immutable resources shipped with the install (config templates, registry)
- mutable run workspace (artifacts, logs, task memory)
"""
from __future__ import annotations

import os
from pathlib import Path


ENV_RESOURCE_ROOT = "MHD_RESOURCE_ROOT"
ENV_WORKSPACE_ROOT = "MHD_WORKSPACE_ROOT"
ENV_CONFIG_PATH = "MHD_CONFIG_PATH"
ENV_TOOL_REGISTRY_PATH = "MHD_TOOL_REGISTRY_PATH"
ENV_ENV_FILE = "MHD_ENV_FILE"


def resource_root() -> Path:
    value = os.getenv(ENV_RESOURCE_ROOT)
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    value = os.getenv(ENV_WORKSPACE_ROOT)
    if value:
        return Path(value).expanduser().resolve()
    return Path.cwd().resolve()


def artifacts_root() -> Path:
    return workspace_root() / "artifacts"


def generated_root() -> Path:
    return artifacts_root() / "generated"


def task_memory_root() -> Path:
    return artifacts_root() / "task_memory"


def default_config_path() -> Path:
    value = os.getenv(ENV_CONFIG_PATH)
    if value:
        return Path(value).expanduser().resolve()
    return (resource_root() / "config" / "runtime.yaml").resolve()


def default_tool_registry_path() -> Path:
    value = os.getenv(ENV_TOOL_REGISTRY_PATH)
    if value:
        return Path(value).expanduser().resolve()
    return (resource_root() / "tool_registry.yaml").resolve()


def default_env_file() -> Path:
    value = os.getenv(ENV_ENV_FILE)
    if value:
        return Path(value).expanduser().resolve()
    return (workspace_root() / ".env").resolve()
