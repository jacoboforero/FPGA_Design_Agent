"""
Tests for Pydantic models in the schemas package.
"""
import pytest
from datetime import datetime, timezone
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


class TestCostMetrics:
    """Test cases for CostMetrics model."""
    
    def test_valid_cost_metrics(self):
        """Test creating valid CostMetrics."""
        metrics = CostMetrics(
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05
        )
        
        assert metrics.input_tokens == 1000
        assert metrics.output_tokens == 500
        assert metrics.cost_usd == 0.05
    
    def test_cost_metrics_validation(self):
        """Test CostMetrics validation."""
        # Valid case
        metrics = CostMetrics(input_tokens=100, output_tokens=50, cost_usd=0.01)
        assert isinstance(metrics, CostMetrics)
        
        # Test with zero values
        metrics_zero = CostMetrics(input_tokens=0, output_tokens=0, cost_usd=0.0)
        assert metrics_zero.input_tokens == 0
        assert metrics_zero.output_tokens == 0
        assert metrics_zero.cost_usd == 0.0
    
    def test_cost_metrics_invalid_types(self):
        """Test CostMetrics with invalid types."""
        with pytest.raises(ValidationError):
            CostMetrics(input_tokens="invalid", output_tokens=50, cost_usd=0.01)
        
        with pytest.raises(ValidationError):
            CostMetrics(input_tokens=100, output_tokens="invalid", cost_usd=0.01)
        
        with pytest.raises(ValidationError):
            CostMetrics(input_tokens=100, output_tokens=50, cost_usd="invalid")
    
    def test_cost_metrics_negative_values(self):
        """Test CostMetrics with negative values."""
        # Negative values should be allowed (for error cases)
        metrics = CostMetrics(input_tokens=-100, output_tokens=-50, cost_usd=-0.01)
        assert metrics.input_tokens == -100
        assert metrics.output_tokens == -50
        assert metrics.cost_usd == -0.01


class TestTaskMessage:
    """Test cases for TaskMessage model."""
    
    def test_task_message_minimal_creation(self, sample_context):
        """Test creating TaskMessage with minimal required fields."""
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context=sample_context
        )
        
        assert isinstance(task.task_id, UUID)
        assert isinstance(task.correlation_id, UUID)
        assert isinstance(task.created_at, datetime)
        assert task.priority == TaskPriority.MEDIUM
        assert task.entity_type == EntityType.REASONING
        assert task.task_type == AgentType.PLANNER
        assert task.context == sample_context
    
    def test_task_message_with_all_fields(self, sample_context):
        """Test creating TaskMessage with all fields specified."""
        task_id = uuid4()
        correlation_id = uuid4()
        created_at = datetime.now(timezone.utc)
        
        task = TaskMessage(
            task_id=task_id,
            correlation_id=correlation_id,
            created_at=created_at,
            priority=TaskPriority.HIGH,
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=WorkerType.LINTER,
            context=sample_context
        )
        
        assert task.task_id == task_id
        assert task.correlation_id == correlation_id
        assert task.created_at == created_at
        assert task.priority == TaskPriority.HIGH
        assert task.entity_type == EntityType.LIGHT_DETERMINISTIC
        assert task.task_type == WorkerType.LINTER
        assert task.context == sample_context
    
    def test_task_message_agent_types(self, sample_context):
        """Test TaskMessage with different agent types."""
        for agent_type in AgentType:
            task = TaskMessage(
                entity_type=EntityType.REASONING,
                task_type=agent_type,
                context=sample_context
            )
            assert task.entity_type == EntityType.REASONING
            assert task.task_type == agent_type
    
    def test_task_message_worker_types(self, sample_context):
        """Test TaskMessage with different worker types."""
        for worker_type in WorkerType:
            task = TaskMessage(
                entity_type=EntityType.LIGHT_DETERMINISTIC,
                task_type=worker_type,
                context=sample_context
            )
            assert task.entity_type == EntityType.LIGHT_DETERMINISTIC
            assert task.task_type == worker_type
    
    def test_task_message_priorities(self, sample_context):
        """Test TaskMessage with different priorities."""
        for priority in TaskPriority:
            task = TaskMessage(
                entity_type=EntityType.REASONING,
                task_type=AgentType.PLANNER,
                priority=priority,
                context=sample_context
            )
            assert task.priority == priority
    
    def test_task_message_validation_errors(self, sample_context):
        """Test TaskMessage validation errors."""
        # Missing required fields
        with pytest.raises(ValidationError):
            TaskMessage()
        
        with pytest.raises(ValidationError):
            TaskMessage(entity_type=EntityType.REASONING, context=sample_context)
        
        with pytest.raises(ValidationError):
            TaskMessage(task_type=AgentType.PLANNER, context=sample_context)
        
        with pytest.raises(ValidationError):
            TaskMessage(entity_type=EntityType.REASONING, task_type=AgentType.PLANNER)
    
    def test_task_message_context_types(self):
        """Test TaskMessage with different context types."""
        # Test with various context structures
        contexts = [
            {"simple": "value"},
            {"nested": {"key": "value"}},
            {"list": [1, 2, 3]},
            {"mixed": {"str": "value", "int": 42, "bool": True}},
            {}  # Empty context
        ]
        
        for context in contexts:
            task = TaskMessage(
                entity_type=EntityType.REASONING,
                task_type=AgentType.PLANNER,
                context=context
            )
            assert task.context == context


class TestResultMessage:
    """Test cases for ResultMessage model."""
    
    def test_result_message_minimal_creation(self, sample_task_id, sample_correlation_id):
        """Test creating ResultMessage with minimal required fields."""
        result = ResultMessage(
            task_id=sample_task_id,
            correlation_id=sample_correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Task completed successfully"
        )
        
        assert result.task_id == sample_task_id
        assert result.correlation_id == sample_correlation_id
        assert isinstance(result.completed_at, datetime)
        assert result.status == TaskStatus.SUCCESS
        assert result.log_output == "Task completed successfully"
        assert result.artifacts_path is None
        assert result.reflections is None
        assert result.metrics is None
    
    def test_result_message_with_all_fields(self, sample_task_id, sample_correlation_id, sample_cost_metrics):
        """Test creating ResultMessage with all fields specified."""
        completed_at = datetime.now(timezone.utc)
        
        result = ResultMessage(
            task_id=sample_task_id,
            correlation_id=sample_correlation_id,
            completed_at=completed_at,
            status=TaskStatus.FAILURE,
            artifacts_path="/path/to/artifacts",
            log_output="Task failed with error",
            reflections="Need to investigate the root cause",
            metrics=sample_cost_metrics
        )
        
        assert result.task_id == sample_task_id
        assert result.correlation_id == sample_correlation_id
        assert result.completed_at == completed_at
        assert result.status == TaskStatus.FAILURE
        assert result.artifacts_path == "/path/to/artifacts"
        assert result.log_output == "Task failed with error"
        assert result.reflections == "Need to investigate the root cause"
        assert result.metrics == sample_cost_metrics
    
    def test_result_message_status_types(self, sample_task_id, sample_correlation_id):
        """Test ResultMessage with different status types."""
        for status in TaskStatus:
            result = ResultMessage(
                task_id=sample_task_id,
                correlation_id=sample_correlation_id,
                status=status,
                log_output=f"Task completed with status: {status.value}"
            )
            assert result.status == status
    
    def test_result_message_validation_errors(self, sample_task_id, sample_correlation_id):
        """Test ResultMessage validation errors."""
        # Missing required fields
        with pytest.raises(ValidationError):
            ResultMessage()
        
        with pytest.raises(ValidationError):
            ResultMessage(task_id=sample_task_id, correlation_id=sample_correlation_id)
        
        with pytest.raises(ValidationError):
            ResultMessage(task_id=sample_task_id, status=TaskStatus.SUCCESS)
        
        with pytest.raises(ValidationError):
            ResultMessage(correlation_id=sample_correlation_id, status=TaskStatus.SUCCESS)
    
    def test_result_message_optional_fields(self, sample_task_id, sample_correlation_id):
        """Test ResultMessage with optional fields."""
        # Test with None values for optional fields
        result = ResultMessage(
            task_id=sample_task_id,
            correlation_id=sample_correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Success",
            artifacts_path=None,
            reflections=None,
            metrics=None
        )
        
        assert result.artifacts_path is None
        assert result.reflections is None
        assert result.metrics is None
    
    def test_result_message_with_metrics(self, sample_task_id, sample_correlation_id, sample_cost_metrics):
        """Test ResultMessage with cost metrics."""
        result = ResultMessage(
            task_id=sample_task_id,
            correlation_id=sample_correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Task completed",
            metrics=sample_cost_metrics
        )
        
        assert result.metrics == sample_cost_metrics
        assert result.metrics.input_tokens == 1000
        assert result.metrics.output_tokens == 500
        assert result.metrics.cost_usd == 0.05


class TestModelIntegration:
    """Test integration between different models."""
    
    def test_task_to_result_relationship(self, sample_context):
        """Test the relationship between TaskMessage and ResultMessage."""
        # Create a task
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.PLANNER,
            context=sample_context
        )
        
        # Create a corresponding result
        result = ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Planning completed successfully"
        )
        
        # Verify the IDs match
        assert result.task_id == task.task_id
        assert result.correlation_id == task.correlation_id
    
    def test_agent_task_with_metrics(self, sample_context):
        """Test agent task with cost metrics."""
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.IMPLEMENTATION,
            context=sample_context
        )
        
        cost_metrics = CostMetrics(
            input_tokens=2000,
            output_tokens=1000,
            cost_usd=0.10
        )
        
        result = ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Implementation completed",
            metrics=cost_metrics
        )
        
        assert result.metrics == cost_metrics
        assert result.status == TaskStatus.SUCCESS
    
    def test_worker_task_without_metrics(self, sample_context):
        """Test worker task without cost metrics."""
        task = TaskMessage(
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=WorkerType.SIMULATOR,
            context=sample_context
        )
        
        result = ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Simulation completed",
            artifacts_path="/path/to/simulation_results"
        )
        
        assert result.metrics is None  # This test doesn't include cost metrics
        assert result.artifacts_path == "/path/to/simulation_results"
