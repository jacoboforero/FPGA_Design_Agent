"""
Schema-specific pytest configuration and fixtures.
"""
import pytest
from datetime import datetime
from uuid import UUID, uuid4
from schemas import (
    TaskPriority,
    TaskStatus,
    EntityType,
    AgentType,
    WorkerType,
    CostMetrics,
    TaskMessage,
    ResultMessage,
)


@pytest.fixture
def sample_task_id():
    """Provide a sample task ID for testing."""
    return uuid4()


@pytest.fixture
def sample_correlation_id():
    """Provide a sample correlation ID for testing."""
    return uuid4()


@pytest.fixture
def sample_context():
    """Provide a sample context dictionary for testing."""
    return {
        "node_id": "test_node_123",
        "specs": {"frequency": "100MHz", "area": "1000um2"},
        "code_paths": ["/path/to/design.v", "/path/to/testbench.v"]
    }


@pytest.fixture
def sample_cost_metrics():
    """Provide sample cost metrics for testing."""
    return CostMetrics(
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.05
    )
