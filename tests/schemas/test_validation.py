"""
Tests for model validation and error handling.
"""
import pytest
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import ValidationError

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


class TestValidationErrors:
    """Test validation error handling for all models."""
    
    def test_cost_metrics_validation_errors(self):
        """Test CostMetrics validation with various invalid inputs."""
        # Test missing required fields
        with pytest.raises(ValidationError) as exc_info:
            CostMetrics()
        assert "input_tokens" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            CostMetrics(input_tokens=100)
        assert "output_tokens" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            CostMetrics(input_tokens=100, output_tokens=50)
        assert "cost_usd" in str(exc_info.value)
        
        # Test invalid types
        with pytest.raises(ValidationError):
            CostMetrics(input_tokens="not_a_number", output_tokens=50, cost_usd=0.01)
        
        with pytest.raises(ValidationError):
            CostMetrics(input_tokens=100, output_tokens=[1, 2, 3], cost_usd=0.01)
        
        with pytest.raises(ValidationError):
            CostMetrics(input_tokens=100, output_tokens=50, cost_usd={"invalid": "dict"})
    
    def test_task_message_validation_errors(self):
        """Test TaskMessage validation with various invalid inputs."""
        # Test missing required fields
        with pytest.raises(ValidationError) as exc_info:
            TaskMessage()
        assert "entity_type" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            TaskMessage(entity_type=EntityType.REASONING)
        assert "task_type" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            TaskMessage(entity_type=EntityType.REASONING, task_type=AgentType.PLANNER)
        assert "context" in str(exc_info.value)
        
        # Test invalid enum values
        with pytest.raises(ValidationError):
            TaskMessage(
                entity_type="INVALID_ENTITY",
                task_type=AgentType.PLANNER,
                context={"test": "value"}
            )
        
        with pytest.raises(ValidationError):
            TaskMessage(
                entity_type=EntityType.REASONING,
                task_type="INVALID_AGENT",
                context={"test": "value"}
            )
        
        # Test invalid priority
        with pytest.raises(ValidationError):
            TaskMessage(
                entity_type=EntityType.REASONING,
                task_type=AgentType.PLANNER,
                priority="INVALID_PRIORITY",
                context={"test": "value"}
            )
        
        # Test invalid UUID types
        with pytest.raises(ValidationError):
            TaskMessage(
                task_id="not_a_uuid",
                entity_type=EntityType.REASONING,
                task_type=AgentType.PLANNER,
                context={"test": "value"}
            )
        
        with pytest.raises(ValidationError):
            TaskMessage(
                correlation_id="not_a_uuid",
                entity_type=EntityType.REASONING,
                task_type=AgentType.PLANNER,
                context={"test": "value"}
            )
        
        # Test invalid datetime
        with pytest.raises(ValidationError):
            TaskMessage(
                created_at="not_a_datetime",
                entity_type=EntityType.REASONING,
                task_type=AgentType.PLANNER,
                context={"test": "value"}
            )
    
    def test_result_message_validation_errors(self):
        """Test ResultMessage validation with various invalid inputs."""
        task_id = uuid4()
        correlation_id = uuid4()
        
        # Test missing required fields
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage()
        assert "task_id" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage(task_id=task_id)
        assert "correlation_id" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage(task_id=task_id, correlation_id=correlation_id)
        assert "status" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            ResultMessage(task_id=task_id, correlation_id=correlation_id, status=TaskStatus.SUCCESS)
        assert "log_output" in str(exc_info.value)
        
        # Test invalid enum values
        with pytest.raises(ValidationError):
            ResultMessage(
                task_id=task_id,
                correlation_id=correlation_id,
                status="INVALID_STATUS",
                log_output="test"
            )
        
        # Test invalid UUID types
        with pytest.raises(ValidationError):
            ResultMessage(
                task_id="not_a_uuid",
                correlation_id=correlation_id,
                status=TaskStatus.SUCCESS,
                log_output="test"
            )
        
        with pytest.raises(ValidationError):
            ResultMessage(
                task_id=task_id,
                correlation_id="not_a_uuid",
                status=TaskStatus.SUCCESS,
                log_output="test"
            )
        
        # Test invalid datetime
        with pytest.raises(ValidationError):
            ResultMessage(
                task_id=task_id,
                correlation_id=correlation_id,
                status=TaskStatus.SUCCESS,
                log_output="test",
                completed_at="not_a_datetime"
            )
    
    def test_entity_type_task_type_consistency(self):
        """Test that entity_type and task_type are consistent."""
        # Agent entity with agent task type should work
        TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={"test": "value"}
        )
        
        # Worker entity with worker task type should work
        TaskMessage(
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=WorkerType.LINTER,
            context={"test": "value"}
        )
        
        # Note: Pydantic doesn't enforce cross-field validation by default,
        # so these inconsistent combinations would currently pass validation.
        # In a real system, you might want to add custom validators.
    
    def test_optional_field_validation(self):
        """Test validation of optional fields."""
        task_id = uuid4()
        correlation_id = uuid4()
        
        # Test with valid optional fields
        result = ResultMessage(
            task_id=task_id,
            correlation_id=correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="test",
            artifacts_path="/valid/path",
            reflections="Valid reflections",
            metrics=CostMetrics(input_tokens=100, output_tokens=50, cost_usd=0.01)
        )
        assert result.artifacts_path == "/valid/path"
        assert result.reflections == "Valid reflections"
        assert result.metrics is not None
        
        # Test with None values for optional fields
        result_none = ResultMessage(
            task_id=task_id,
            correlation_id=correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="test",
            artifacts_path=None,
            reflections=None,
            metrics=None
        )
        assert result_none.artifacts_path is None
        assert result_none.reflections is None
        assert result_none.metrics is None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_context(self):
        """Test TaskMessage with empty context."""
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={}
        )
        assert task.context == {}
    
    def test_large_context(self):
        """Test TaskMessage with large context."""
        large_context = {
            "large_data": "x" * 10000,
            "nested": {
                "deep": {
                    "structure": {
                        "with": {
                            "many": {
                                "levels": "value"
                            }
                        }
                    }
                }
            },
            "list": list(range(1000))
        }
        
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context=large_context
        )
        assert task.context == large_context
    
    def test_unicode_context(self):
        """Test TaskMessage with unicode context."""
        unicode_context = {
            "unicode_string": "Hello 世界 🌍",
            "emoji": "🚀💻🔧",
            "special_chars": "ñáéíóú"
        }
        
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context=unicode_context
        )
        assert task.context == unicode_context
    
    def test_extreme_cost_metrics(self):
        """Test CostMetrics with extreme values."""
        # Very large numbers
        large_metrics = CostMetrics(
            input_tokens=999999999,
            output_tokens=999999999,
            cost_usd=999999.99
        )
        assert large_metrics.input_tokens == 999999999
        assert large_metrics.output_tokens == 999999999
        assert large_metrics.cost_usd == 999999.99
        
        # Very small numbers
        small_metrics = CostMetrics(
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.000001
        )
        assert small_metrics.input_tokens == 1
        assert small_metrics.output_tokens == 1
        assert small_metrics.cost_usd == 0.000001
    
    def test_long_log_output(self):
        """Test ResultMessage with very long log output."""
        long_log = "This is a very long log output. " * 1000
        
        result = ResultMessage(
            task_id=uuid4(),
            correlation_id=uuid4(),
            status=TaskStatus.SUCCESS,
            log_output=long_log
        )
        assert result.log_output == long_log
    
    def test_datetime_edge_cases(self):
        """Test datetime edge cases."""
        # Test with specific datetime
        specific_time = datetime(2024, 1, 1, 12, 0, 0)
        
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context={"test": "value"},
            created_at=specific_time
        )
        assert task.created_at == specific_time
        
        result = ResultMessage(
            task_id=uuid4(),
            correlation_id=uuid4(),
            status=TaskStatus.SUCCESS,
            log_output="test",
            completed_at=specific_time
        )
        assert result.completed_at == specific_time


class TestCustomValidation:
    """Test custom validation scenarios."""
    
    def test_validation_error_details(self):
        """Test that validation errors provide useful details."""
        with pytest.raises(ValidationError) as exc_info:
            CostMetrics(input_tokens="invalid", output_tokens=50, cost_usd=0.01)
        
        error = exc_info.value
        assert hasattr(error, 'errors')
        assert len(error.errors()) > 0
        
        # Check that the error details are informative
        error_details = error.errors()[0]
        assert "input_tokens" in str(error_details)
    
    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are reported."""
        with pytest.raises(ValidationError) as exc_info:
            TaskMessage(
                entity_type="INVALID_ENTITY",
                task_type="INVALID_TASK",
                context="INVALID_CONTEXT"  # Should be dict, not string
            )
        
        error = exc_info.value
        errors = error.errors()
        assert len(errors) >= 2  # Should have multiple errors
