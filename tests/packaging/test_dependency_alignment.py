from __future__ import annotations

import re
import tomllib
from pathlib import Path


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def test_homebrew_requirements_are_declared_in_pyproject():
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    poetry_deps = {
        _normalize(name)
        for name in pyproject["tool"]["poetry"]["dependencies"].keys()
        if _normalize(name) != "python"
    }

    requirement_names = set()
    for raw_line in (repo_root / "packaging" / "homebrew" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement_names.add(_normalize(re.split(r"[<>=!~\\[]", line, maxsplit=1)[0]))

    assert requirement_names <= poetry_deps
