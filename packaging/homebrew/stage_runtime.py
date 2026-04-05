#!/usr/bin/env python3
"""
Stage a minimal runtime tree for the Homebrew-installed CLI.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


COPY_DIRS = (
    "adapters",
    "agents",
    "core",
    "orchestrator",
    "workers",
    "apps/cli",
    "config",
    "third_party/verilog-eval/scripts",
    "third_party/verilog-eval/dataset_spec-to-rtl",
)

COPY_FILES = (
    "tool_registry.yaml",
    "third_party/verilog-eval/Makefile.in",
)

INSTALL_MARKER = ".mhd-installed-runtime"


def _ignore(_src: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store"}
        or name.endswith(".pyc")
        or name.endswith(".pyo")
    }
    return ignored


def _copy_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Required runtime directory missing: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=_ignore)


def _copy_file(src: Path, dest: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Required runtime file missing: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def stage_runtime_tree(source_root: Path, dest_root: Path) -> Path:
    source_root = source_root.resolve()
    dest_root = dest_root.resolve()
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    for rel_path in COPY_DIRS:
        _copy_tree(source_root / rel_path, dest_root / rel_path)

    for rel_path in COPY_FILES:
        _copy_file(source_root / rel_path, dest_root / rel_path)

    (dest_root / INSTALL_MARKER).write_text("homebrew-installed-runtime\n", encoding="utf-8")
    return dest_root


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if len(argv) != 2:
        print("usage: stage_runtime.py <source_root> <dest_root>", file=sys.stderr)
        return 2
    stage_runtime_tree(Path(argv[0]), Path(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
