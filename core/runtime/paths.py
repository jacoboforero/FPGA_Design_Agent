"""
Path helpers for developer and installed CLI environments.

The codebase historically assumed it was always run from the repository root.
For Homebrew-style installs we need to distinguish:

- immutable resources shipped with the install (config templates, registry)
- mutable run workspace (artifacts, logs, task memory)
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


ENV_RESOURCE_ROOT = "MHD_RESOURCE_ROOT"
ENV_WORKSPACE_ROOT = "MHD_WORKSPACE_ROOT"
ENV_CONFIG_PATH = "MHD_CONFIG_PATH"
ENV_TOOL_REGISTRY_PATH = "MHD_TOOL_REGISTRY_PATH"
ENV_ENV_FILE = "MHD_ENV_FILE"
ENV_INSTALL_CONTEXT = "MHD_INSTALL_CONTEXT"
ENV_XDG_CONFIG_HOME = "XDG_CONFIG_HOME"
ENV_ACTIVE_CONFIG_ROOT = "MHD_ACTIVE_CONFIG_ROOT"

_INSTALL_MARKER = ".mhd-installed-runtime"
_REQUIRED_CONFIG_ENTRYPOINTS = ("runtime.yaml", "runtime.benchmark.yaml")
_USER_EDITABLE_RUNTIME_FILES = ("tool_registry.yaml",)
_OPTIONAL_CONFIG_TEMPLATES: tuple[str, ...] = ()


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


def rag_artifacts_root() -> Path:
    return artifacts_root() / "rag"


def generated_root() -> Path:
    return artifacts_root() / "generated"


def task_memory_root() -> Path:
    return artifacts_root() / "task_memory"


def is_installed_runtime() -> bool:
    value = os.getenv(ENV_INSTALL_CONTEXT)
    if value:
        return value.strip().lower() not in {"0", "false", "no", "off", "dev"}
    return (resource_root() / _INSTALL_MARKER).exists()


def bundled_config_root() -> Path:
    return (resource_root() / "config").resolve()


def bundled_tool_registry_path() -> Path:
    return (resource_root() / "tool_registry.yaml").resolve()


def user_config_root() -> Path:
    xdg = os.getenv(ENV_XDG_CONFIG_HOME, "").strip()
    base = Path(xdg).expanduser() if xdg else (Path.home() / ".config")
    return (base / "mhd").resolve()


def ensure_user_config_root() -> Path:
    source_root = bundled_config_root()
    target_root = user_config_root()

    missing_source = [source_root / name for name in _REQUIRED_CONFIG_ENTRYPOINTS if not (source_root / name).exists()]
    if missing_source:
        joined = ", ".join(str(path) for path in missing_source)
        raise FileNotFoundError(f"Installed config templates missing required entrypoints: {joined}")

    if not target_root.exists():
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_root, target_root)
        for filename in _USER_EDITABLE_RUNTIME_FILES:
            bundled_path = resource_root() / filename
            target_path = target_root / filename
            if bundled_path.exists():
                shutil.copy2(bundled_path, target_path)
        return target_root

    if not target_root.is_dir():
        raise RuntimeError(
            f"Installed config home exists but is not a directory: {target_root}. "
            "Remove it or set XDG_CONFIG_HOME to a different location."
        )

    missing_target = [target_root / name for name in _REQUIRED_CONFIG_ENTRYPOINTS if not (target_root / name).exists()]
    if missing_target:
        joined = ", ".join(str(path) for path in missing_target)
        raise RuntimeError(
            f"Installed config home is incomplete: missing {joined}. "
            "Restore the missing files or remove the directory so mhd can seed a fresh config tree."
        )
    for filename in _USER_EDITABLE_RUNTIME_FILES:
        bundled_path = resource_root() / filename
        target_path = target_root / filename
        if not target_path.exists() and bundled_path.exists():
            shutil.copy2(bundled_path, target_path)
    for rel_path in _OPTIONAL_CONFIG_TEMPLATES:
        bundled_path = source_root / rel_path
        target_path = target_root / rel_path
        if not target_path.exists() and bundled_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_path, target_path)
    return target_root


def config_root() -> Path:
    if is_installed_runtime():
        return ensure_user_config_root()
    return bundled_config_root()


def default_config_path(config_name: str = "runtime.yaml") -> Path:
    value = os.getenv(ENV_CONFIG_PATH)
    if value:
        return Path(value).expanduser().resolve()
    return (config_root() / config_name).resolve()


def default_benchmark_config_path() -> Path:
    return default_config_path("runtime.benchmark.yaml")


def default_tool_registry_path() -> Path:
    value = os.getenv(ENV_TOOL_REGISTRY_PATH)
    if value:
        return Path(value).expanduser().resolve()
    if is_installed_runtime():
        return (ensure_user_config_root() / "tool_registry.yaml").resolve()
    return bundled_tool_registry_path()


def active_config_root() -> Optional[Path]:
    value = os.getenv(ENV_ACTIVE_CONFIG_ROOT, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def set_active_config_root(path: Optional[Path]) -> None:
    if path is None:
        os.environ.pop(ENV_ACTIVE_CONFIG_ROOT, None)
        return
    os.environ[ENV_ACTIVE_CONFIG_ROOT] = str(Path(path).expanduser().resolve())


def resolve_resource_path(path_like: str | Path) -> Path:
    path = Path(path_like).expanduser()
    if path.is_absolute():
        return path.resolve()
    config_root = active_config_root()
    config_candidate = (config_root / path).resolve() if config_root is not None else None
    resource_candidate = (resource_root() / path).resolve()
    if config_candidate is not None and config_candidate.exists():
        return config_candidate
    if resource_candidate.exists():
        return resource_candidate
    if config_candidate is not None:
        return config_candidate
    return resource_candidate


def resolve_rag_workspace_path(path_like: str | Path) -> Path:
    path = Path(path_like).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (rag_artifacts_root() / path).resolve()


def default_env_file() -> Optional[Path]:
    value = os.getenv(ENV_ENV_FILE)
    if value:
        return Path(value).expanduser().resolve()
    if is_installed_runtime():
        return None
    return (workspace_root() / ".env").resolve()
