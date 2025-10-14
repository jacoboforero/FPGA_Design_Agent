# contracts.py
# Version: 1.0.0
# Author: Jacobo Forero
# Description: This file defines the core data contracts for the asynchronous
# multi-agent hardware design system. All communication between the Orchestrator
# and the various execution entities (Agents and Workers) MUST adhere to these
# schemas.

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# --- Controlled Vocabularies (Enums) ---
# Using enums prevents ambiguity and typos in key fields.

class TaskPriority(Enum):
    """Defines the execution priority of a task."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3

class TaskStatus(Enum):
    """Defines the outcome status of a completed task."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    ESCALATED = "ESCALATED_TO_HUMAN"

class EntityType(Enum):
    """Distinguishes between intelligent LLM-based agents and deterministic workers."""
    AGENT = "AGENT"
    WORKER = "WORKER"

class AgentType(Enum):
    """Specifies which LLM-based agent should execute the task."""
    PLANNER = "PlannerAgent"
    IMPLEMENTATION = "ImplementationAgent"
    TESTBENCH = "TestbenchAgent"
    DEBUG = "DebugAgent"
    INTEGRATION = "IntegrationAgent"

class WorkerType(Enum):
    """Specifies which deterministic worker should execute the task."""
    LINTER = "LinterWorker"
    SIMULATOR = "SimulatorWorker"
    SYNTHESIZER = "SynthesizerWorker"


# --- Sub-Models for Composition ---

class CostMetrics(BaseModel):
    """A structured model for tracking LLM-related costs, to be embedded in results."""
    input_tokens: int
    output_tokens: int
    cost_usd: float = Field(..., description="Calculated cost in USD for this specific operation.")


# --- Core Message Schemas ---

class TaskMessage(BaseModel):
    """
    The fundamental unit of work sent from the Orchestrator to the Task Broker.
    This schema defines a task to be executed by either an Agent or a Worker.
    """
    task_id: UUID = Field(default_factory=uuid4, description="Unique identifier for this specific task instance.")
    correlation_id: UUID = Field(default_factory=uuid4, description="Identifier to trace a chain of related tasks (e.g., implement -> test -> debug).")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp in UTC when the task was created.")

    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Execution priority.")

    # Task Routing Fields
    entity_type: EntityType = Field(..., description="The type of entity that should process this task (Agent or Worker).")
    task_type: Union[AgentType, WorkerType] = Field(..., description="The specific type of Agent or Worker to invoke.")

    # Payload
    context: Dict[str, Any] = Field(..., description="The payload containing all necessary data for the task (e.g., node_id, specs, code paths). Will be specialized into specific models later.")


class ResultMessage(BaseModel):
    """
    The fundamental unit of result sent from an Agent or Worker back to the Orchestrator.
    This schema defines the outcome of a completed task.
    """
    task_id: UUID = Field(..., description="The ID of the task this result corresponds to.")
    correlation_id: UUID = Field(..., description="The correlation ID from the original task for end-to-end tracing.")
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp in UTC when the task was completed.")

    status: TaskStatus = Field(..., description="The final outcome of the task.")

    # Output Artifacts
    artifacts_path: Optional[str] = Field(None, description="Path (e.g., S3 URI or shared volume path) to any generated artifacts like code or reports.")
    log_output: str = Field(..., description="A summary or the full stdout/stderr from the task execution.")

    # Optional fields for specific use cases
    reflections: Optional[str] = Field(None, description="For agents (especially DebugAgent), a reflection on the task outcome.")
    metrics: Optional[CostMetrics] = Field(None, description="Cost and token usage information, primarily for agent tasks.")