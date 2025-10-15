# Multi-Agent Hardware Design System - Schema Documentation

**Version:** 1.0.1  
**Author:** Jacobo Forero  
**Team:** Jacobo Forero, Dexter Pressley, Mateus Verffel Mayer, Caleb Elliott, Andrew Chambers, Sammy Fares

## Overview

This document defines the core data contracts for the multi-agent hardware design system. These schemas define the structure of messages and data used throughout the system.

## Schema Categories

### 1. Controlled Vocabularies (Enums)

These enums prevent ambiguity and typos in key fields across the system.

### 2. Data Models

Pydantic models that define the structure of messages and data.

---

## 📋 **Controlled Vocabularies (Enums)**

### **TaskPriority**

Defines the execution priority of a task.

| Value        | Description                    |
| ------------ | ------------------------------ |
| `LOW = 1`    | Low priority task              |
| `MEDIUM = 2` | Medium priority task (default) |
| `HIGH = 3`   | High priority task             |

### **TaskStatus**

Defines the outcome status of a completed task.

| Value                              | Description                      |
| ---------------------------------- | -------------------------------- |
| `SUCCESS = "SUCCESS"`              | Task completed successfully      |
| `FAILURE = "FAILURE"`              | Task failed to complete          |
| `ESCALATED = "ESCALATED_TO_HUMAN"` | Task requires human intervention |

### **EntityType**

Distinguishes between different types of processing entities based on their characteristics.

| Value                                         | Description                                          |
| --------------------------------------------- | ---------------------------------------------------- |
| `REASONING = "REASONING"`                     | LLM-based agents requiring creativity and reasoning  |
| `LIGHT_DETERMINISTIC = "LIGHT_DETERMINISTIC"` | Fast, lightweight deterministic tasks                |
| `HEAVY_DETERMINISTIC = "HEAVY_DETERMINISTIC"` | Resource-intensive, long-running deterministic tasks |

### **AgentType**

Specifies which LLM-based agent should execute the task.

| Value                                    | Description                          |
| ---------------------------------------- | ------------------------------------ |
| `PLANNER = "PlannerAgent"`               | High-level planning and architecture |
| `IMPLEMENTATION = "ImplementationAgent"` | Code generation and implementation   |
| `TESTBENCH = "TestbenchAgent"`           | Test case generation and validation  |
| `DEBUG = "DebugAgent"`                   | Problem diagnosis and debugging      |
| `INTEGRATION = "IntegrationAgent"`       | System integration and deployment    |

### **WorkerType**

Specifies which deterministic worker should execute the task.

| Value                               | Description                          |
| ----------------------------------- | ------------------------------------ |
| `LINTER = "LinterWorker"`           | Code linting and style checking      |
| `SIMULATOR = "SimulatorWorker"`     | Hardware simulation and verification |
| `SYNTHESIZER = "SynthesizerWorker"` | Logic synthesis and optimization     |

---

## 📊 **Data Models**

### **CostMetrics**

A structured model for tracking LLM-related costs, embedded in results.

| Field           | Type    | Required | Description                               |
| --------------- | ------- | -------- | ----------------------------------------- |
| `input_tokens`  | `int`   | ✅       | Number of input tokens consumed           |
| `output_tokens` | `int`   | ✅       | Number of output tokens generated         |
| `cost_usd`      | `float` | ✅       | Calculated cost in USD for this operation |

### **TaskMessage**

The fundamental unit of work in the system.

| Field            | Type                      | Required | Default        | Description                                                                                           |
| ---------------- | ------------------------- | -------- | -------------- | ----------------------------------------------------------------------------------------------------- |
| `task_id`        | `UUID`                    | ✅       | Auto-generated | Unique identifier for this specific task instance                                                     |
| `correlation_id` | `UUID`                    | ✅       | Auto-generated | Identifier to trace a chain of related tasks                                                          |
| `created_at`     | `datetime`                | ✅       | Auto-generated | Timestamp in UTC when the task was created                                                            |
| `priority`       | `TaskPriority`            | ✅       | `MEDIUM`       | Execution priority                                                                                    |
| `entity_type`    | `EntityType`              | ✅       | -              | Type of entity that should process this task (REASONING, LIGHT_DETERMINISTIC, or HEAVY_DETERMINISTIC) |
| `task_type`      | `AgentType \| WorkerType` | ✅       | -              | Specific type of Agent or Worker to invoke                                                            |
| `context`        | `Dict[str, Any]`          | ✅       | -              | Payload containing all necessary data for the task                                                    |

**Example TaskMessage:**

```python
{
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "correlation_id": "987fcdeb-51a2-43d1-b789-123456789abc",
    "created_at": "2024-01-15T10:30:00Z",
    "priority": "HIGH",
    "entity_type": "REASONING",
    "task_type": "PlannerAgent",
    "context": {
        "node_id": "design_123",
        "specs": {"frequency": "100MHz", "area": "1000um2"},
        "code_paths": ["/path/to/design.v", "/path/to/testbench.v"]
    }
}
```

### **ResultMessage**

The fundamental unit of result in the system.

| Field            | Type          | Required | Default        | Description                                       |
| ---------------- | ------------- | -------- | -------------- | ------------------------------------------------- |
| `task_id`        | `UUID`        | ✅       | -              | The ID of the task this result corresponds to     |
| `correlation_id` | `UUID`        | ✅       | -              | The correlation ID from the original task         |
| `completed_at`   | `datetime`    | ✅       | Auto-generated | Timestamp in UTC when the task was completed      |
| `status`         | `TaskStatus`  | ✅       | -              | The final outcome of the task                     |
| `artifacts_path` | `str`         | ❌       | `None`         | Path to any generated artifacts                   |
| `log_output`     | `str`         | ✅       | -              | Summary or full stdout/stderr from task execution |
| `reflections`    | `str`         | ❌       | `None`         | For agents, a reflection on the task outcome      |
| `metrics`        | `CostMetrics` | ❌       | `None`         | Cost and token usage information                  |

**Example ResultMessage:**

```python
{
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "correlation_id": "987fcdeb-51a2-43d1-b789-123456789abc",
    "completed_at": "2024-01-15T10:35:00Z",
    "status": "SUCCESS",
    "artifacts_path": "/path/to/generated_code.v",
    "log_output": "Task completed successfully. Generated 150 lines of Verilog.",
    "reflections": "The implementation follows best practices for clock domain crossing.",
    "metrics": {
        "input_tokens": 2000,
        "output_tokens": 1000,
        "cost_usd": 0.10
    }
}
```

---

## 🔄 **Schema Relationships**

### **TaskMessage → ResultMessage:**

- `ResultMessage.task_id` must match `TaskMessage.task_id`
- `ResultMessage.correlation_id` must match `TaskMessage.correlation_id`
- This enables linking results back to their originating tasks

### **Entity Type Consistency:**

- When `TaskMessage.entity_type = EntityType.AGENT`, then `task_type` must be an `AgentType`
- When `TaskMessage.entity_type = EntityType.WORKER`, then `task_type` must be a `WorkerType`

---

## 🛠 **Usage Examples**

### **Importing Schemas:**

```python
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
```

### **Creating a Task:**

```python
task = TaskMessage(
    entity_type=EntityType.REASONING,
    task_type=AgentType.PLANNER,
    priority=TaskPriority.HIGH,
    context={
        "node_id": "design_123",
        "specs": {"frequency": "100MHz"}
    }
)
```

### **Creating a Result:**

```python
result = ResultMessage(
    task_id=task.task_id,
    correlation_id=task.correlation_id,
    status=TaskStatus.SUCCESS,
    log_output="Planning completed successfully",
    metrics=CostMetrics(
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.05
    )
)
```

---

## ✅ **Validation & Testing**

- **100% Test Coverage** - All schemas are thoroughly tested
- **Pydantic Validation** - Automatic type checking and validation
- **JSON Serialization** - Full serialization/deserialization support
- **Edge Case Handling** - Comprehensive error handling and validation

**Test Coverage:**

- 67 comprehensive tests
- All enums, models, validation, and serialization tested
- Edge cases and error scenarios covered

---

## 📝 **Schema Versioning**

- **Current Version:** 1.0.1
- **Backward Compatibility:** Maintained through careful field evolution
- **Breaking Changes:** Will increment major version number
- **Documentation:** All changes tracked in this document
