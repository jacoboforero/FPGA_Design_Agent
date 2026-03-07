"""
Global pytest configuration and shared fixtures for the multi-agent hardware design system.
"""
import pytest
from datetime import datetime
from uuid import UUID, uuid4
from core.runtime.config import get_runtime_config, set_runtime_config
from core.schemas import (
    TaskPriority,
    TaskStatus,
    EntityType,
    AgentType,
    WorkerType,
    CostMetrics,
    TaskMessage,
    ResultMessage,
)


# Global fixtures for system-wide testing
# Component-specific fixtures are in their respective conftest.py files


@pytest.fixture(autouse=True)
def _restore_runtime_config():
    baseline = get_runtime_config().model_copy(deep=True)
    yield
    set_runtime_config(baseline)
