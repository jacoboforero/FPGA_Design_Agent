"""
Context builder for demo tasks. Given a node id, returns the payload attached
to TaskMessage with interface, rtl path, and design context hash.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class DemoContextBuilder:
    def __init__(self, design_context_path: Path, rtl_root: Path) -> None:
        self.design_context_path = design_context_path
        self.rtl_root = rtl_root
        self._context = json.loads(design_context_path.read_text())

    def build(self, node_id: str) -> Dict[str, Any]:
        node = self._context["nodes"][node_id]
        rtl_path = self.rtl_root / node["rtl_file"]
        tb_path = node.get("testbench_file")
        if not tb_path:
            tb_path = rtl_path.with_name(f"{node_id}_tb.sv")
        else:
            tb_path = self.rtl_root / tb_path
        return {
            "node_id": node_id,
            "interface": node["interface"],
            "rtl_path": str(rtl_path),
            "tb_path": str(tb_path),
            "design_context_hash": self._context["design_context_hash"],
            "coverage_goals": node.get("coverage_goals", {}),
            "clocking": node.get("clocking", {}),
            "library_refs": self._context.get("standard_library", {}),
            "demo_behavior": node.get("demo_behavior", "passthrough"),
            "verification": node.get("verification", {}),
            "acceptance": node.get("acceptance", {}),
        }
