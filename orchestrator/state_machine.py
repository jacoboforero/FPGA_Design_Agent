"""
Lightweight state machine and models for demo DAG nodes.
This is a simplified stand-in for the full artifact lifecycle.
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional


class NodeState(str, Enum):
    PENDING = "PENDING"
    IMPLEMENTING = "IMPLEMENTING"
    LINTING = "LINTING"
    TESTBENCHING = "TESTBENCHING"
    SIMULATING = "SIMULATING"
    DISTILLING = "DISTILLING"
    REFLECTING = "REFLECTING"
    DEBUGGING = "DEBUGGING"
    DONE = "DONE"
    FAILED = "FAILED"


ALLOWED_TRANSITIONS = {
    NodeState.PENDING: {NodeState.IMPLEMENTING},
    NodeState.IMPLEMENTING: {NodeState.LINTING, NodeState.FAILED},
    NodeState.LINTING: {NodeState.TESTBENCHING, NodeState.FAILED},
    NodeState.TESTBENCHING: {NodeState.SIMULATING, NodeState.FAILED},
    NodeState.SIMULATING: {NodeState.DISTILLING, NodeState.DONE, NodeState.FAILED},
    NodeState.DISTILLING: {NodeState.REFLECTING, NodeState.FAILED},
    NodeState.REFLECTING: {NodeState.DEBUGGING, NodeState.FAILED},
    NodeState.DEBUGGING: {NodeState.FAILED},
}


@dataclass
class Node:
    node_id: str
    state: NodeState = NodeState.PENDING
    artifacts: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, str] = field(default_factory=dict)

    def transition(self, new_state: NodeState) -> None:
        if new_state not in ALLOWED_TRANSITIONS.get(self.state, {}):
            raise ValueError(f"Illegal transition {self.state} -> {new_state}")
        self.state = new_state
