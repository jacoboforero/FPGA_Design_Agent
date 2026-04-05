from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_stage_runtime_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "packaging" / "homebrew" / "stage_runtime.py"
    spec = importlib.util.spec_from_file_location("stage_runtime", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_runtime_copies_only_required_payload(tmp_path):
    module = _load_stage_runtime_module()
    repo_root = Path(__file__).resolve().parents[2]
    dest_root = tmp_path / "runtime"

    module.stage_runtime_tree(repo_root, dest_root)

    assert (dest_root / "adapters").is_dir()
    assert (dest_root / "agents").is_dir()
    assert (dest_root / "apps" / "cli").is_dir()
    assert (dest_root / "config" / "runtime.yaml").exists()
    assert (dest_root / "tool_registry.yaml").exists()
    assert (dest_root / "third_party" / "verilog-eval" / "scripts" / "sv-iv-analyze").exists()
    assert (dest_root / "third_party" / "verilog-eval" / "dataset_spec-to-rtl").is_dir()
    assert (dest_root / module.INSTALL_MARKER).exists()

    assert not (dest_root / "apps" / "ui_backend").exists()
    assert not (dest_root / "apps" / "vscode-extension").exists()
    assert not (dest_root / "docs").exists()
    assert not (dest_root / "tests").exists()
    assert not (dest_root / "infrastructure").exists()
    assert not (dest_root / ".env").exists()
    assert not (dest_root / "packaging").exists()


def test_formula_no_longer_pins_opt_homebrew_etc_runtime():
    formula_path = Path(__file__).resolve().parents[2] / "packaging" / "homebrew" / "Formula" / "mhd.rb"
    text = formula_path.read_text(encoding="utf-8")

    assert "/opt/homebrew/etc/mhd/runtime.yaml" not in text
    assert "MHD_CONFIG_PATH" not in text
    assert "stage_runtime.py" in text
