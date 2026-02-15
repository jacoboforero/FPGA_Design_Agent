from orchestrator.state_machine import Node, NodeState


def test_pending_can_transition_to_failed_for_blocked_dependents():
    node = Node("n0")
    node.transition(NodeState.FAILED)
    assert node.state is NodeState.FAILED


def test_invalid_transition_still_raises():
    node = Node("n1")
    try:
        node.transition(NodeState.SIMULATING)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid transition")
