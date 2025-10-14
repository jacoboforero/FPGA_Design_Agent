"""
Global pytest configuration and shared fixtures for the multi-agent hardware design system.
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


# Global fixtures for system-wide testing
# Component-specific fixtures are in their respective conftest.py files
