from __future__ import annotations

import json
from typing import Any


def build_implementation_rag_query(
    *,
    node_id: str,
    iface: list[dict],
    behavior: str,
    verification: dict,
    module_contract: dict,
    children: list[Any],
    child_interfaces: dict[str, Any],
    connections: list[Any],
) -> str:
    interface_summary = []
    for signal in iface:
        if not isinstance(signal, dict):
            continue
        interface_summary.append(
            f"{signal.get('direction', 'signal')} {signal.get('name', 'unnamed')} width={signal.get('width', 1)}"
        )
    verification_goals = verification.get("test_goals") if isinstance(verification.get("test_goals"), list) else []
    lines = [
        f"implementation query for module {node_id}",
        "interface:",
        *[f"- {item}" for item in interface_summary[:24]],
        f"behavior: {behavior or 'none provided'}",
        f"module_contract: {json.dumps(module_contract, sort_keys=True)}",
        f"verification_goals: {json.dumps(verification_goals[:8])}",
    ]
    if children:
        lines.append(f"children: {json.dumps(children[:12])}")
        lines.append(f"child_interfaces: {json.dumps(child_interfaces, sort_keys=True)}")
    if connections:
        lines.append(f"connections: {json.dumps(connections[:24], sort_keys=True)}")
    return "\n".join(lines)
