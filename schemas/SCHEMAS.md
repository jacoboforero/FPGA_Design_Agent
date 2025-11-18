# Multi-Agent Hardware Design System - Schema Documentation

**Version:** 1.2.0  
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

| Value                                               | Description                            |
| --------------------------------------------------- | -------------------------------------- |
| `PLANNER = "PlannerAgent"`                          | High-level planning and architecture   |
| `IMPLEMENTATION = "ImplementationAgent"`            | Code generation and implementation     |
| `TESTBENCH = "TestbenchAgent"`                      | Test case generation and validation    |
| `DEBUG = "DebugAgent"`                              | Problem diagnosis and debugging        |
| `INTEGRATION = "IntegrationAgent"`                  | System integration and deployment      |
| `REFLECTION = "ReflectionAgent"`                    | AI-powered analysis of distilled data  |
| `SPECIFICATION_HELPER = "SpecificationHelperAgent"` | Specification convergence and guidance |

### **WorkerType**

Specifies which deterministic worker should execute the task.

| Value                                 | Description                                    |
| ------------------------------------- | ---------------------------------------------- |
| `LINTER = "LinterWorker"`             | Code linting and style checking                |
| `SIMULATOR = "SimulatorWorker"`       | Hardware simulation and verification           |
| `SYNTHESIZER = "SynthesizerWorker"`   | Logic synthesis and optimization               |
| `DISTILLATION = "DistillationWorker"` | Waveform/log data distillation and compression |

---

## 📊 **Data Models**

### **CostMetrics**

A structured model for tracking LLM-related costs, embedded in results.

| Field           | Type    | Required | Description                               |
| --------------- | ------- | -------- | ----------------------------------------- |
| `input_tokens`  | `int`   | ✅       | Number of input tokens consumed           |
| `output_tokens` | `int`   | ✅       | Number of output tokens generated         |
| `cost_usd`      | `float` | ✅       | Calculated cost in USD for this operation |

### **AnalysisMetadata**

Metadata for analysis pipeline stages including timestamps, failure signatures, and retry counts.

| Field                    | Type             | Required | Description                                                      |
| ------------------------ | ---------------- | -------- | ---------------------------------------------------------------- |
| `stage`                  | `str`            | ✅       | Analysis stage: distill, reflect, or debug                       |
| `timestamp`              | `datetime`       | ✅       | When this analysis stage was executed                            |
| `failure_signature`      | `str`            | ❌       | Unique identifier for the type of failure observed               |
| `retry_count`            | `int`            | ✅       | Number of retry attempts for this analysis stage                 |
| `upstream_artifact_refs` | `Dict[str, str]` | ❌       | References to upstream artifacts (e.g., distilled dataset paths) |

### **DistilledDataset**

Structured representation of distilled waveform/log data.

| Field                 | Type        | Required | Description                                           |
| --------------------- | ----------- | -------- | ----------------------------------------------------- |
| `dataset_id`          | `UUID`      | ✅       | Unique identifier for this distilled dataset          |
| `original_data_size`  | `int`       | ✅       | Size of original waveform/log data in bytes           |
| `distilled_data_size` | `int`       | ✅       | Size of distilled data in bytes                       |
| `compression_ratio`   | `float`     | ✅       | Ratio of original to distilled size                   |
| `failure_focus_areas` | `list[str]` | ✅       | List of failure-relevant areas identified in the data |
| `data_path`           | `str`       | ✅       | Path to the distilled dataset file                    |
| `created_at`          | `datetime`  | ✅       | When the distillation was completed                   |

### **ReflectionInsights**

Structured insights produced by the Reflection Agent.

| Field                   | Type        | Required | Description                                         |
| ----------------------- | ----------- | -------- | --------------------------------------------------- |
| `reflection_id`         | `UUID`      | ✅       | Unique identifier for this reflection               |
| `hypotheses`            | `list[str]` | ✅       | List of root-cause hypotheses                       |
| `likely_failure_points` | `list[str]` | ✅       | Identified likely failure points in the design      |
| `recommended_probes`    | `list[str]` | ✅       | Recommended debugging probes or investigation paths |
| `confidence_score`      | `float`     | ✅       | Confidence in the analysis (0.0 to 1.0)             |
| `analysis_notes`        | `str`       | ✅       | Detailed analysis notes for downstream debugging    |
| `created_at`            | `datetime`  | ✅       | When the reflection was completed                   |

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

| Field                 | Type                 | Required | Default        | Description                                       |
| --------------------- | -------------------- | -------- | -------------- | ------------------------------------------------- |
| `task_id`             | `UUID`               | ✅       | -              | The ID of the task this result corresponds to     |
| `correlation_id`      | `UUID`               | ✅       | -              | The correlation ID from the original task         |
| `completed_at`        | `datetime`           | ✅       | Auto-generated | Timestamp in UTC when the task was completed      |
| `status`              | `TaskStatus`         | ✅       | -              | The final outcome of the task                     |
| `artifacts_path`      | `str`                | ❌       | `None`         | Path to any generated artifacts                   |
| `log_output`          | `str`                | ✅       | -              | Summary or full stdout/stderr from task execution |
| `reflections`         | `str`                | ❌       | `None`         | For agents, a reflection on the task outcome      |
| `metrics`             | `CostMetrics`        | ❌       | `None`         | Cost and token usage information                  |
| `analysis_metadata`   | `AnalysisMetadata`   | ❌       | `None`         | Metadata for analysis pipeline stages             |
| `distilled_dataset`   | `DistilledDataset`   | ❌       | `None`         | Distilled dataset from distillation tasks         |
| `reflection_insights` | `ReflectionInsights` | ❌       | `None`         | Structured insights from reflection tasks         |

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
    },
    "analysis_metadata": {
        "stage": "reflect",
        "timestamp": "2024-01-15T10:35:00Z",
        "failure_signature": "timing_violation_001",
        "retry_count": 0,
        "upstream_artifact_refs": {
            "distilled_dataset": "/path/to/distilled_data.json"
        }
    },
    "distilled_dataset": {
        "dataset_id": "456e7890-e89b-12d3-a456-426614174001",
        "original_data_size": 1048576,
        "distilled_data_size": 262144,
        "compression_ratio": 0.25,
        "failure_focus_areas": ["clock_domain_crossing", "setup_violation"],
        "data_path": "/path/to/distilled_data.json",
        "created_at": "2024-01-15T10:30:00Z"
    },
    "reflection_insights": {
        "reflection_id": "789e0123-e89b-12d3-a456-426614174002",
        "hypotheses": ["Clock domain crossing violation", "Setup time violation"],
        "likely_failure_points": ["CDC_FF_inst", "Data path delay"],
        "recommended_probes": ["CDC_FF_inst.Q", "clk_to_data_delay"],
        "confidence_score": 0.85,
        "analysis_notes": "High confidence in clock domain crossing issue based on timing analysis",
        "created_at": "2024-01-15T10:35:00Z"
    }
}
```

- [Specification Models](#specification-models-l1-l5)

### **Specification Models (L1-L5)**

Tier‑1 planning artifacts are modeled in `schemas/specifications.py`. They extend a shared `SpecificationDocument` base (metadata such as `spec_id`, `state`, `revision`, `created_by`, `approved_by`, content hash, and upstream references). Each level adds its own payload:

| Model             | Purpose                          | Key Fields                                                                                                                                                                             |
| ----------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `L1Specification` | Functional intent                | `role_summary`, `key_rules`, `performance_intent`, `reset_semantics`, `corner_cases`, `open_questions`                                                                                 |
| `L2Specification` | Interface contract               | `clocking` (list of `ClockingInfo` entries with clock/reset polarity), `signals` (direction + width expression), `handshake_semantics`, `transaction_unit`, `configuration_parameters` |
| `L3Specification` | Verification plan                | `test_goals`, `oracle_strategy`, `stimulus_strategy`, `pass_fail_criteria`, `coverage_targets`, `reset_constraints`, `scenarios`                                                       |
| `L4Specification` | Architecture / microarchitecture | `block_diagram` nodes, `dependencies`, `clock_domains`, `resource_strategy`, `latency_budget`, `assertion_plan`                                                                        |
| `L5Specification` | Acceptance & sign-off plan       | `required_artifacts`, `acceptance_metrics` (operator/target pairs keyed to L3 coverage IDs), `exclusions`, `synthesis_target`                                                          |

The immutable bundle of approved levels is represented by `FrozenSpecification` (captures references to the frozen L1–L5 documents plus the design-context artifact URI). All five child documents must be in `FROZEN` state and share the same `spec_id`, enabling Tier‑1 persistence to be read safely by downstream agents.

Supporting enums/classes include:

- `SpecificationLevel`, `SpecificationState`
- `ClockPolarity`, `ResetPolarity`, `ClockingInfo`
- `SignalDirection`, `SignalDefinition`, `HandshakeProtocol`, `ConfigurationParameter`
- `VerificationScenario`, `CoverageTarget`, `ResetConstraint`
- `BlockDiagramNode`, `DependencyEdge`, `ClockDomain`, `AssertionPlan`
- `ArtifactRequirement`, `AcceptanceMetric`

These models formalize the L1–L5 checklist described in `docs/spec-and-planning.md` and should be used whenever persisting or validating planning artifacts.

---

## 🔄 **Schema Relationships**

### **TaskMessage → ResultMessage:**

- `ResultMessage.task_id` must match `TaskMessage.task_id`
- `ResultMessage.correlation_id` must match `TaskMessage.correlation_id`
- This enables linking results back to their originating tasks

### **Entity Type Consistency:**

- When `TaskMessage.entity_type = EntityType.REASONING`, then `task_type` must be an `AgentType`
- When `TaskMessage.entity_type = EntityType.LIGHT_DETERMINISTIC` or `EntityType.HEAVY_DETERMINISTIC`, then `task_type` must be a `WorkerType`

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
    AnalysisMetadata,
    DistilledDataset,
    ReflectionInsights,
    TaskMessage,
    ResultMessage,
)
```

### **Creating a Task:**

```python
# Planning task
task = TaskMessage(
    entity_type=EntityType.REASONING,
    task_type=AgentType.PLANNER,
    priority=TaskPriority.HIGH,
    context={
        "node_id": "design_123",
        "specs": {"frequency": "100MHz"}
    }
)

# Reflection task for analysis pipeline
reflection_task = TaskMessage(
    entity_type=EntityType.REASONING,
    task_type=AgentType.REFLECTION,
    priority=TaskPriority.MEDIUM,
    context={
        "node_id": "design_123",
        "distilled_dataset_path": "/path/to/distilled_data.json",
        "failure_context": "timing_violation_001"
    }
)

# Distillation task for data processing
distillation_task = TaskMessage(
    entity_type=EntityType.LIGHT_DETERMINISTIC,
    task_type=WorkerType.DISTILLATION,
    priority=TaskPriority.MEDIUM,
    context={
        "node_id": "design_123",
        "waveform_path": "/path/to/waveform.vcd",
        "log_path": "/path/to/simulation.log"
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

- **Current Version:** 1.1.0
- **Backward Compatibility:** Maintained through careful field evolution
- **Breaking Changes:** Will increment major version number
- **Documentation:** All changes tracked in this document

### **Version 1.2.0 Changes:**

- Added Tier-1 planning schemas (`SpecificationDocument`, `L1`–`L5` models, supporting enums, and `FrozenSpecification`) to capture the complete L1–L5 checklist and Design Context artifacts.
- Documented these models in the Specification Models section.

### **Version 1.1.0 Changes:**

- Added `REFLECTION` and `SPECIFICATION_HELPER` agent types
- Added `DISTILLATION` worker type
- Added new analysis pipeline models: `AnalysisMetadata`, `DistilledDataset`, `ReflectionInsights`
- Enhanced `ResultMessage` with analysis pipeline artifacts
- Updated documentation with new examples and usage patterns
