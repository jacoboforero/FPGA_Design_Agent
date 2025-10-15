"""
Tests for JSON serialization and deserialization of schemas.
"""
import json
import pytest
from datetime import datetime, timezone
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


class TestJSONSerialization:
    """Test JSON serialization of all models."""
    
    def test_cost_metrics_serialization(self):
        """Test CostMetrics JSON serialization."""
        metrics = CostMetrics(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05
        )
        
        json_str = metrics.model_dump_json()
        data = json.loads(json_str)
        
        assert data["input_tokens"] == 1000
        assert data["output_tokens"] == 500
        assert data["cost_usd"] == 0.05
    
    def test_task_message_serialization(self):
        """Test TaskMessage JSON serialization."""
        task_id = uuid4()
        correlation_id = uuid4()
        created_at = datetime.now(timezone.utc)
        
        task = TaskMessage(
            task_id=task_id,
            correlation_id=correlation_id,
            created_at=created_at,
            priority=TaskPriority.HIGH,
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={"test": "value", "nested": {"key": "value"}}
        )
        
        json_str = task.model_dump_json()
        data = json.loads(json_str)
        
        assert data["task_id"] == str(task_id)
        assert data["correlation_id"] == str(correlation_id)
        assert data["priority"] == TaskPriority.HIGH.value
        assert data["entity_type"] == EntityType.REASONING.value
        assert data["task_type"] == AgentType.PLANNER.value
        assert data["context"] == {"test": "value", "nested": {"key": "value"}}
        assert "created_at" in data
    
    def test_result_message_serialization(self):
        """Test ResultMessage JSON serialization."""
        task_id = uuid4()
        correlation_id = uuid4()
        completed_at = datetime.now(timezone.utc)
        
        metrics = CostMetrics(input_tokens=100, output_tokens=50, cost_usd=0.01)
        
        result = ResultMessage(
            task_id=task_id,
            correlation_id=correlation_id,
            completed_at=completed_at,
            status=TaskStatus.SUCCESS,
            artifacts_path="/path/to/artifacts",
            log_output="Task completed successfully",
            reflections="All good",
            metrics=metrics
        )
        
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        
        assert data["task_id"] == str(task_id)
        assert data["correlation_id"] == str(correlation_id)
        assert data["status"] == TaskStatus.SUCCESS.value
        assert data["artifacts_path"] == "/path/to/artifacts"
        assert data["log_output"] == "Task completed successfully"
        assert data["reflections"] == "All good"
        assert data["metrics"]["input_tokens"] == 100
        assert data["metrics"]["output_tokens"] == 50
        assert data["metrics"]["cost_usd"] == 0.01
        assert "completed_at" in data
    
    def test_enum_serialization(self):
        """Test that enums are serialized correctly."""
        # Test individual enum serialization - enums serialize to their values
        assert TaskPriority.HIGH.value == 3
        assert TaskStatus.SUCCESS.value == "SUCCESS"
        assert EntityType.REASONING.value == "REASONING"
        assert AgentType.PLANNER.value == "PlannerAgent"
        assert WorkerType.LINTER.value == "LinterWorker"
    
    def test_serialization_with_none_values(self):
        """Test serialization with None values for optional fields."""
        result = ResultMessage(
            task_id=uuid4(),
            correlation_id=uuid4(),
            status=TaskStatus.SUCCESS,
            log_output="test",
            artifacts_path=None,
            reflections=None,
            metrics=None
        )
        
        json_str = result.model_dump_json()
        data = json.loads(json_str)
        
        assert data["artifacts_path"] is None
        assert data["reflections"] is None
        assert data["metrics"] is None


class TestJSONDeserialization:
    """Test JSON deserialization of all models."""
    
    def test_cost_metrics_deserialization(self):
        """Test CostMetrics JSON deserialization."""
        json_data = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cost_usd": 0.05
        }
        
        metrics = CostMetrics.model_validate(json_data)
        assert metrics.input_tokens == 1000
        assert metrics.output_tokens == 500
        assert metrics.cost_usd == 0.05
    
    def test_task_message_deserialization(self):
        """Test TaskMessage JSON deserialization."""
        task_id = str(uuid4())
        correlation_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        
        json_data = {
            "task_id": task_id,
            "correlation_id": correlation_id,
            "created_at": created_at,
            "priority": TaskPriority.HIGH.value,
            "entity_type": EntityType.REASONING.value,
            "task_type": AgentType.PLANNER.value,
            "context": {"test": "value"}
        }
        
        task = TaskMessage.model_validate(json_data)
        assert str(task.task_id) == task_id
        assert str(task.correlation_id) == correlation_id
        assert task.priority == TaskPriority.HIGH
        assert task.entity_type == EntityType.REASONING
        assert task.task_type == AgentType.PLANNER
        assert task.context == {"test": "value"}
    
    def test_result_message_deserialization(self):
        """Test ResultMessage JSON deserialization."""
        task_id = str(uuid4())
        correlation_id = str(uuid4())
        completed_at = datetime.now(timezone.utc).isoformat()
        
        json_data = {
            "task_id": task_id,
            "correlation_id": correlation_id,
            "completed_at": completed_at,
            "status": TaskStatus.SUCCESS.value,
            "artifacts_path": "/path/to/artifacts",
            "log_output": "Task completed",
            "reflections": "All good",
            "metrics": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01
            }
        }
        
        result = ResultMessage.model_validate(json_data)
        assert str(result.task_id) == task_id
        assert str(result.correlation_id) == correlation_id
        assert result.status == TaskStatus.SUCCESS
        assert result.artifacts_path == "/path/to/artifacts"
        assert result.log_output == "Task completed"
        assert result.reflections == "All good"
        assert result.metrics.input_tokens == 100
        assert result.metrics.output_tokens == 50
        assert result.metrics.cost_usd == 0.01
    
    def test_enum_deserialization(self):
        """Test enum deserialization from JSON."""
        # Test deserializing enum values - enums can be created from their values
        assert TaskPriority(3) == TaskPriority.HIGH
        assert TaskStatus("SUCCESS") == TaskStatus.SUCCESS
        assert EntityType("REASONING") == EntityType.REASONING
        assert AgentType("PlannerAgent") == AgentType.PLANNER
        assert WorkerType("LinterWorker") == WorkerType.LINTER


class TestRoundTripSerialization:
    """Test round-trip serialization and deserialization."""
    
    def test_cost_metrics_round_trip(self):
        """Test CostMetrics round-trip serialization."""
        original = CostMetrics(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05
        )
        
        json_str = original.model_dump_json()
        deserialized = CostMetrics.model_validate_json(json_str)
        
        assert deserialized.input_tokens == original.input_tokens
        assert deserialized.output_tokens == original.output_tokens
        assert deserialized.cost_usd == original.cost_usd
    
    def test_task_message_round_trip(self):
        """Test TaskMessage round-trip serialization."""
        original = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={"test": "value", "nested": {"key": "value"}}
        )
        
        json_str = original.model_dump_json()
        deserialized = TaskMessage.model_validate_json(json_str)
        
        assert deserialized.task_id == original.task_id
        assert deserialized.correlation_id == original.correlation_id
        assert deserialized.priority == original.priority
        assert deserialized.entity_type == original.entity_type
        assert deserialized.task_type == original.task_type
        assert deserialized.context == original.context
        # Note: datetime comparison might have microsecond differences
        assert abs((deserialized.created_at - original.created_at).total_seconds()) < 1
    
    def test_result_message_round_trip(self):
        """Test ResultMessage round-trip serialization."""
        metrics = CostMetrics(input_tokens=100, output_tokens=50, cost_usd=0.01)
        
        original = ResultMessage(
            task_id=uuid4(),
            correlation_id=uuid4(),
            status=TaskStatus.SUCCESS,
            artifacts_path="/path/to/artifacts",
            log_output="Task completed",
            reflections="All good",
            metrics=metrics
        )
        
        json_str = original.model_dump_json()
        deserialized = ResultMessage.model_validate_json(json_str)
        
        assert deserialized.task_id == original.task_id
        assert deserialized.correlation_id == original.correlation_id
        assert deserialized.status == original.status
        assert deserialized.artifacts_path == original.artifacts_path
        assert deserialized.log_output == original.log_output
        assert deserialized.reflections == original.reflections
        assert deserialized.metrics.input_tokens == original.metrics.input_tokens
        assert deserialized.metrics.output_tokens == original.metrics.output_tokens
        assert deserialized.metrics.cost_usd == original.metrics.cost_usd
        # Note: datetime comparison might have microsecond differences
        assert abs((deserialized.completed_at - original.completed_at).total_seconds()) < 1
    
    def test_complex_context_round_trip(self):
        """Test round-trip with complex context data."""
        complex_context = {
            "strings": ["hello", "world"],
            "numbers": [1, 2, 3, 4, 5],
            "nested": {
                "level1": {
                    "level2": {
                        "level3": "deep_value"
                    }
                }
            },
            "unicode": "Hello 世界 🌍",
            "special_chars": "ñáéíóú",
            "empty_list": [],
            "empty_dict": {},
            "boolean": True,
            "null_value": None
        }
        
        original = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context=complex_context
        )
        
        json_str = original.model_dump_json()
        deserialized = TaskMessage.model_validate_json(json_str)
        
        assert deserialized.context == original.context
        assert deserialized.context["unicode"] == "Hello 世界 🌍"
        assert deserialized.context["special_chars"] == "ñáéíóú"
        assert deserialized.context["nested"]["level1"]["level2"]["level3"] == "deep_value"


class TestSerializationEdgeCases:
    """Test serialization edge cases and special scenarios."""
    
    def test_serialization_with_datetime_objects(self):
        """Test serialization with specific datetime objects."""
        specific_time = datetime(2024, 1, 1, 12, 0, 0, 123456)
        
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={"test": "value"},
            created_at=specific_time
        )
        
        json_str = task.model_dump_json()
        data = json.loads(json_str)
        
        # Check that datetime is serialized as ISO format
        assert "created_at" in data
        assert isinstance(data["created_at"], str)
        
        # Deserialize and verify
        deserialized = TaskMessage.model_validate_json(json_str)
        assert deserialized.created_at == specific_time
    
    def test_serialization_with_uuid_objects(self):
        """Test serialization with specific UUID objects."""
        specific_task_id = uuid4()
        specific_correlation_id = uuid4()
        
        task = TaskMessage(
            task_id=specific_task_id,
            correlation_id=specific_correlation_id,
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={"test": "value"}
        )
        
        json_str = task.model_dump_json()
        data = json.loads(json_str)
        
        # Check that UUIDs are serialized as strings
        assert data["task_id"] == str(specific_task_id)
        assert data["correlation_id"] == str(specific_correlation_id)
        
        # Deserialize and verify
        deserialized = TaskMessage.model_validate_json(json_str)
        assert deserialized.task_id == specific_task_id
        assert deserialized.correlation_id == specific_correlation_id
    
    def test_serialization_performance(self):
        """Test serialization performance with large data."""
        # Create a task with large context
        large_context = {
            "large_string": "x" * 10000,
            "large_list": list(range(1000)),
            "nested_data": {
                f"key_{i}": f"value_{i}" for i in range(100)
            }
        }
        
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context=large_context
        )
        
        # Test serialization
        json_str = task.model_dump_json()
        assert len(json_str) > 10000  # Should be a large JSON string
        
        # Test deserialization
        deserialized = TaskMessage.model_validate_json(json_str)
        assert deserialized.context == large_context
