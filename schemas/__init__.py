# /schemas/__init__.py

# Set the version for your data contracts.
# This allows you to track changes to the schemas themselves.
__version__ = "1.0.0"

# Import the core models to the top level of the package.
# This allows other developers to write `from schemas import TaskMessage`
# instead of the longer `from schemas.contracts import TaskMessage`.
from .contracts import (
    TaskPriority,
    TaskStatus,
    EntityType,
    AgentType,
    WorkerType,
    CostMetrics,
    TaskMessage,
    ResultMessage,
)

__all__ = [
    "__version__",
    "TaskPriority",
    "TaskStatus",
    "EntityType",
    "AgentType",
    "WorkerType",
    "CostMetrics",
    "TaskMessage",
    "ResultMessage",
]