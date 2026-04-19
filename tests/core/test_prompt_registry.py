from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.prompting import PromptRegistry, render_prompt


def test_repo_prompt_registry_loads_all_bundles_and_fragments():
    registry = PromptRegistry()
    prompt_ids = {item.prompt_id for item in registry.list_prompts()}
    bundle_count = len(list(registry.root.rglob("meta.yaml")))
    fragment_paths = [
        path.relative_to(registry.root / "fragments").as_posix()
        for path in sorted((registry.root / "fragments").rglob("*.md"))
    ]
    fragment_contexts = {
        "implementation/contract/combinational.md": {"always_keyword": "always @(*)"},
    }

    assert len(prompt_ids) == bundle_count
    assert "spec_helper.extract" in prompt_ids
    assert "implementation.generate" in prompt_ids
    assert "narrator.card" in prompt_ids
    assert fragment_paths
    for fragment_path in fragment_paths:
        assert registry.render_fragment(fragment_path, fragment_contexts.get(fragment_path))


def test_render_prompt_snapshot_for_implementation_bundle():
    prompt = render_prompt(
        "implementation.generate",
        {
            "rtl_language_rules": "Generate synthesizable Verilog-2001.",
            "contract_rules": "",
            "integration_rules": "",
            "rag_guidance": "",
            "node_id": "demo",
            "port_lines": "- input clk\n- output out",
            "behavior_label": "Behavior summary",
            "behavior": "Drive out low after reset.",
            "clocking_json": "{}",
            "verification_json": "{}",
            "acceptance_json": "{}",
            "module_contract_json": "{}",
            "children_json": "[]",
            "child_interfaces_json": "{}",
            "connections_json": "[]",
        },
    )

    assert prompt.messages[0].content.startswith("You are an RTL Implementation Agent.")
    assert "Generate synthesizable Verilog-2001." in prompt.messages[0].content
    assert "Module name: demo" in prompt.messages[1].content
    assert "Ports:\n- input clk\n- output out" in prompt.messages[1].content


def test_prompt_registry_rejects_duplicate_ids(tmp_path: Path):
    root = tmp_path / "prompts"
    bundle_a = root / "alpha" / "a"
    bundle_b = root / "beta" / "b"
    bundle_a.mkdir(parents=True)
    bundle_b.mkdir(parents=True)
    for bundle in (bundle_a, bundle_b):
        (bundle / "system.md").write_text("hello", encoding="utf-8")
    (bundle_a / "meta.yaml").write_text("id: demo.prompt\nversion: v1\n", encoding="utf-8")
    (bundle_b / "meta.yaml").write_text("id: demo.prompt\nversion: v2\n", encoding="utf-8")

    registry = PromptRegistry(root)
    with pytest.raises(ValueError, match="Duplicate prompt id"):
        registry.list_prompts()


def test_prompt_registry_rejects_invalid_metadata(tmp_path: Path):
    root = tmp_path / "prompts"
    bundle = root / "alpha" / "a"
    bundle.mkdir(parents=True)
    (bundle / "meta.yaml").write_text(
        yaml.safe_dump({"id": "demo.prompt", "version": "v1", "output": {"mode": "invalid_mode"}}),
        encoding="utf-8",
    )
    (bundle / "system.md").write_text("hello", encoding="utf-8")

    registry = PromptRegistry(root)
    with pytest.raises(Exception, match="output_mode"):
        registry.list_prompts()


def test_render_prompt_requires_all_placeholders(tmp_path: Path):
    root = tmp_path / "prompts"
    bundle = root / "alpha" / "a"
    bundle.mkdir(parents=True)
    (bundle / "meta.yaml").write_text("id: demo.prompt\nversion: v1\n", encoding="utf-8")
    (bundle / "system.md").write_text("hello $name", encoding="utf-8")

    registry = PromptRegistry(root)
    with pytest.raises(KeyError):
        registry.render("demo.prompt", {})
