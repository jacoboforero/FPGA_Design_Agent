from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.config import resolve_runtime_config_path
from core.runtime.paths import (
    ENV_ACTIVE_CONFIG_ROOT,
    ENV_CONFIG_PATH,
    ENV_ENV_FILE,
    ENV_INSTALL_CONTEXT,
    ENV_RESOURCE_ROOT,
    ENV_WORKSPACE_ROOT,
    ENV_XDG_CONFIG_HOME,
    default_benchmark_config_path,
    default_config_path,
    default_env_file,
    resolve_resource_path,
)


def _clear_runtime_env(monkeypatch) -> None:
    for name in (
        ENV_CONFIG_PATH,
        ENV_ENV_FILE,
        ENV_INSTALL_CONTEXT,
        ENV_RESOURCE_ROOT,
        ENV_WORKSPACE_ROOT,
        ENV_XDG_CONFIG_HOME,
        ENV_ACTIVE_CONFIG_ROOT,
    ):
        monkeypatch.delenv(name, raising=False)


def _write_config_tree(root: Path) -> None:
    config_root = root / "config"
    domains = config_root / "domains"
    run_dir = config_root / "run"
    domains.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    (config_root / "runtime.yaml").write_text(
        "\n".join(
            [
                "includes:",
                "  - run/engineer.yaml",
                "  - domains/infrastructure.yaml",
            ]
        ),
        encoding="utf-8",
    )
    (config_root / "runtime.benchmark.yaml").write_text(
        "\n".join(
            [
                "includes:",
                "  - run/benchmark.yaml",
                "  - domains/infrastructure.yaml",
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "engineer.yaml").write_text(
        "\n".join(
            [
                "run:",
                "  spec_profile:",
                "    interaction: interactive",
                "    rigor_level: L2",
                "  verification_profile: testbench-agent",
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "benchmark.yaml").write_text(
        "\n".join(
            [
                "run:",
                "  spec_profile:",
                "    interaction: non_interactive",
                "    rigor_level: L0",
                "  verification_profile: verilog-eval",
            ]
        ),
        encoding="utf-8",
    )
    (domains / "infrastructure.yaml").write_text(
        "\n".join(
            [
                "infrastructure:",
                "  broker:",
                "    url: amqp://example/",
            ]
        ),
        encoding="utf-8",
    )


def test_dev_default_paths_stay_repo_local(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv(ENV_WORKSPACE_ROOT, str(tmp_path))

    expected_root = Path(__file__).resolve().parents[2]
    assert default_config_path() == (expected_root / "config" / "runtime.yaml").resolve()
    assert default_benchmark_config_path() == (expected_root / "config" / "runtime.benchmark.yaml").resolve()
    assert default_env_file() == (tmp_path / ".env").resolve()


def test_installed_config_seeds_xdg_home(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    xdg_home = tmp_path / "xdg"
    _write_config_tree(resource_root)
    (resource_root / ".mhd-installed-runtime").write_text("homebrew\n", encoding="utf-8")

    monkeypatch.setenv(ENV_INSTALL_CONTEXT, "1")
    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))
    monkeypatch.setenv(ENV_XDG_CONFIG_HOME, str(xdg_home))

    resolved = default_config_path()
    seeded_root = xdg_home / "mhd"
    assert resolved == (seeded_root / "runtime.yaml").resolve()
    assert (seeded_root / "runtime.yaml").exists()
    assert (seeded_root / "runtime.benchmark.yaml").exists()


def test_existing_installed_user_config_is_not_overwritten(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    xdg_home = tmp_path / "xdg"
    seeded_root = xdg_home / "mhd"
    _write_config_tree(resource_root)
    (resource_root / ".mhd-installed-runtime").write_text("homebrew\n", encoding="utf-8")
    seeded_root.mkdir(parents=True)
    (seeded_root / "runtime.yaml").write_text("run:\n  verification_profile: testbench-agent\n", encoding="utf-8")
    (seeded_root / "runtime.benchmark.yaml").write_text("run:\n  verification_profile: verilog-eval\n", encoding="utf-8")

    monkeypatch.setenv(ENV_INSTALL_CONTEXT, "1")
    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))
    monkeypatch.setenv(ENV_XDG_CONFIG_HOME, str(xdg_home))

    resolved = default_config_path()
    assert resolved == (seeded_root / "runtime.yaml").resolve()
    assert "verification_profile: testbench-agent" in (seeded_root / "runtime.yaml").read_text(encoding="utf-8")


def test_installed_falls_back_to_home_config(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    fake_home = tmp_path / "home"
    _write_config_tree(resource_root)
    (resource_root / ".mhd-installed-runtime").write_text("homebrew\n", encoding="utf-8")

    monkeypatch.setenv(ENV_INSTALL_CONTEXT, "1")
    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    resolved = default_config_path()
    assert resolved == (fake_home / ".config" / "mhd" / "runtime.yaml").resolve()


def test_explicit_config_override_wins(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    explicit = tmp_path / "custom.yaml"
    explicit.write_text("run: {}\n", encoding="utf-8")

    monkeypatch.setenv(ENV_CONFIG_PATH, str(explicit))

    assert default_config_path() == explicit.resolve()
    assert resolve_runtime_config_path(None, default_name="runtime.benchmark.yaml") == explicit.resolve()


def test_installed_default_env_file_is_disabled(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    _write_config_tree(resource_root)
    (resource_root / ".mhd-installed-runtime").write_text("homebrew\n", encoding="utf-8")

    monkeypatch.setenv(ENV_INSTALL_CONTEXT, "1")
    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))

    assert default_env_file() is None


def test_explicit_env_file_override_still_works(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    env_path = tmp_path / "custom.env"
    env_path.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")

    monkeypatch.setenv(ENV_INSTALL_CONTEXT, "1")
    monkeypatch.setenv(ENV_ENV_FILE, str(env_path))

    assert default_env_file() == env_path.resolve()


def test_incomplete_installed_user_config_fails_clearly(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    xdg_home = tmp_path / "xdg"
    user_config = xdg_home / "mhd"
    _write_config_tree(resource_root)
    (resource_root / ".mhd-installed-runtime").write_text("homebrew\n", encoding="utf-8")
    user_config.mkdir(parents=True)
    (user_config / "runtime.yaml").write_text("run: {}\n", encoding="utf-8")

    monkeypatch.setenv(ENV_INSTALL_CONTEXT, "1")
    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))
    monkeypatch.setenv(ENV_XDG_CONFIG_HOME, str(xdg_home))

    with pytest.raises(RuntimeError, match="Installed config home is incomplete"):
        default_benchmark_config_path()


def test_resolve_resource_path_prefers_active_config_root(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    config_root = tmp_path / "config"
    resource_root.mkdir()
    config_root.mkdir()
    (resource_root / "demo_kb.txt").write_text("resource copy\n", encoding="utf-8")
    (config_root / "demo_kb.txt").write_text("config copy\n", encoding="utf-8")

    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))
    monkeypatch.setenv(ENV_ACTIVE_CONFIG_ROOT, str(config_root))

    assert resolve_resource_path("demo_kb.txt") == (config_root / "demo_kb.txt").resolve()


def test_resolve_resource_path_falls_back_to_resource_root(monkeypatch, tmp_path):
    _clear_runtime_env(monkeypatch)
    resource_root = tmp_path / "resource"
    config_root = tmp_path / "config"
    resource_root.mkdir()
    config_root.mkdir()
    (resource_root / "adapters" / "rag").mkdir(parents=True)
    (resource_root / "adapters" / "rag" / "verilog_knowledge_base.txt").write_text(
        "placeholder\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(ENV_RESOURCE_ROOT, str(resource_root))
    monkeypatch.setenv(ENV_ACTIVE_CONFIG_ROOT, str(config_root))

    assert resolve_resource_path("adapters/rag/verilog_knowledge_base.txt") == (
        resource_root / "adapters" / "rag" / "verilog_knowledge_base.txt"
    ).resolve()
