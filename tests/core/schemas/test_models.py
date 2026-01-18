"""
Tests for Pydantic models in the schemas package.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import ValidationError

from core.schemas import (
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


class TestAnalysisMetadata:
    """Test cases for AnalysisMetadata model."""
    
    def test_valid_analysis_metadata(self):
        """Test creating valid AnalysisMetadata."""
        metadata = AnalysisMetadata(
            stage="reflect",
            failure_signature="timing_violation_001",
            retry_count=2,
            upstream_artifact_refs={"distilled_dataset": "/path/to/data.json"}
        )
        
        assert metadata.stage == "reflect"
        assert metadata.failure_signature == "timing_violation_001"
        assert metadata.retry_count == 2
        assert metadata.upstream_artifact_refs == {"distilled_dataset": "/path/to/data.json"}
        assert isinstance(metadata.timestamp, datetime)
    
    def test_analysis_metadata_minimal(self):
        """Test creating AnalysisMetadata with minimal required fields."""
        metadata = AnalysisMetadata(stage="distill")
        
        assert metadata.stage == "distill"
        assert metadata.failure_signature is None
        assert metadata.retry_count == 0
        assert metadata.upstream_artifact_refs is None
        assert isinstance(metadata.timestamp, datetime)
    
    def test_analysis_metadata_validation_errors(self):
        """Test AnalysisMetadata validation errors."""
        with pytest.raises(ValidationError):
            AnalysisMetadata()  # Missing required stage field
        
        with pytest.raises(ValidationError):
            AnalysisMetadata(stage=123)  # Invalid stage type
        
        with pytest.raises(ValidationError):
            AnalysisMetadata(stage="reflect", retry_count="invalid")  # Invalid retry_count type


class TestDistilledDataset:
    """Test cases for DistilledDataset model."""
    
    def test_valid_distilled_dataset(self):
        """Test creating valid DistilledDataset."""
        dataset = DistilledDataset(
            original_data_size=1048576,
            distilled_data_size=262144,
            compression_ratio=0.25,
            failure_focus_areas=["clock_domain_crossing", "setup_violation"],
            data_path="/path/to/distilled_data.json"
        )
        
        assert dataset.original_data_size == 1048576
        assert dataset.distilled_data_size == 262144
        assert dataset.compression_ratio == 0.25
        assert dataset.failure_focus_areas == ["clock_domain_crossing", "setup_violation"]
        assert dataset.data_path == "/path/to/distilled_data.json"
        assert isinstance(dataset.dataset_id, UUID)
        assert isinstance(dataset.created_at, datetime)
    
    def test_distilled_dataset_validation_errors(self):
        """Test DistilledDataset validation errors."""
        with pytest.raises(ValidationError):
            DistilledDataset()  # Missing required fields
        
        with pytest.raises(ValidationError):
            DistilledDataset(
                original_data_size="invalid",
                distilled_data_size=262144,
                compression_ratio=0.25,
                failure_focus_areas=["test"],
                data_path="/path/to/data.json"
            )
        
        with pytest.raises(ValidationError):
            DistilledDataset(
                original_data_size=1048576,
                distilled_data_size=262144,
                compression_ratio="invalid",
                failure_focus_areas=["test"],
                data_path="/path/to/data.json"
            )
    
    def test_distilled_dataset_edge_cases(self):
        """Test DistilledDataset with edge cases."""
        # Test with empty failure focus areas
        dataset = DistilledDataset(
            original_data_size=100,
            distilled_data_size=50,
            compression_ratio=0.5,
            failure_focus_areas=[],
            data_path="/path/to/data.json"
        )
        assert dataset.failure_focus_areas == []
        
        # Test with zero compression
        dataset_zero = DistilledDataset(
            original_data_size=100,
            distilled_data_size=100,
            compression_ratio=1.0,
            failure_focus_areas=["no_compression"],
            data_path="/path/to/data.json"
        )
        assert dataset_zero.compression_ratio == 1.0


class TestReflectionInsights:
    """Test cases for ReflectionInsights model."""
    
    def test_valid_reflection_insights(self):
        """Test creating valid ReflectionInsights."""
        insights = ReflectionInsights(
            hypotheses=["Clock domain crossing violation", "Setup time violation"],
            likely_failure_points=["CDC_FF_inst", "Data path delay"],
            recommended_probes=["CDC_FF_inst.Q", "clk_to_data_delay"],
            confidence_score=0.85,
            analysis_notes="High confidence in clock domain crossing issue"
        )
        
        assert insights.hypotheses == ["Clock domain crossing violation", "Setup time violation"]
        assert insights.likely_failure_points == ["CDC_FF_inst", "Data path delay"]
        assert insights.recommended_probes == ["CDC_FF_inst.Q", "clk_to_data_delay"]
        assert insights.confidence_score == 0.85
        assert insights.analysis_notes == "High confidence in clock domain crossing issue"
        assert isinstance(insights.reflection_id, UUID)
        assert isinstance(insights.created_at, datetime)
    
    def test_reflection_insights_validation_errors(self):
        """Test ReflectionInsights validation errors."""
        with pytest.raises(ValidationError):
            ReflectionInsights()  # Missing required fields
        
        with pytest.raises(ValidationError):
            ReflectionInsights(
                hypotheses=["test"],
                likely_failure_points=["test"],
                recommended_probes=["test"],
                confidence_score=1.5,  # Invalid: > 1.0
                analysis_notes="test"
            )
        
        with pytest.raises(ValidationError):
            ReflectionInsights(
                hypotheses=["test"],
                likely_failure_points=["test"],
                recommended_probes=["test"],
                confidence_score=-0.1,  # Invalid: < 0.0
                analysis_notes="test"
            )
    
    def test_reflection_insights_edge_cases(self):
        """Test ReflectionInsights with edge cases."""
        # Test with empty lists
        insights = ReflectionInsights(
            hypotheses=[],
            likely_failure_points=[],
            recommended_probes=[],
            confidence_score=0.0,
            analysis_notes=""
        )
        assert insights.hypotheses == []
        assert insights.likely_failure_points == []
        assert insights.recommended_probes == []
        assert insights.confidence_score == 0.0
        assert insights.analysis_notes == ""
        
        # Test with maximum confidence
        insights_max = ReflectionInsights(
            hypotheses=["certain"],
            likely_failure_points=["point"],
            recommended_probes=["probe"],
            confidence_score=1.0,
            analysis_notes="Maximum confidence"
        )
        assert insights_max.confidence_score == 1.0


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
    
    def test_task_message_new_agent_types(self, sample_context):
        """Test TaskMessage with new agent types (REFLECTION and SPECIFICATION_HELPER)."""
        # Test REFLECTION agent
        reflection_task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.REFLECTION,
            context=sample_context
        )
        assert reflection_task.entity_type == EntityType.REASONING
        assert reflection_task.task_type == AgentType.REFLECTION
        
        # Test SPECIFICATION_HELPER agent
        spec_helper_task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.SPECIFICATION_HELPER,
            context=sample_context
        )
        assert spec_helper_task.entity_type == EntityType.REASONING
        assert spec_helper_task.task_type == AgentType.SPECIFICATION_HELPER
    
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
    
    def test_task_message_new_worker_types(self, sample_context):
        """Test TaskMessage with new worker types (DISTILLATION)."""
        # Test DISTILLATION worker
        distillation_task = TaskMessage(
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=WorkerType.DISTILLATION,
            context=sample_context
        )
        assert distillation_task.entity_type == EntityType.LIGHT_DETERMINISTIC
        assert distillation_task.task_type == WorkerType.DISTILLATION
    
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
    
    def test_result_message_with_analysis_pipeline_artifacts(self, sample_task_id, sample_correlation_id):
        """Test ResultMessage with new analysis pipeline artifacts."""
        # Create analysis metadata
        analysis_metadata = AnalysisMetadata(
            stage="reflect",
            failure_signature="timing_violation_001",
            retry_count=1,
            upstream_artifact_refs={"distilled_dataset": "/path/to/data.json"}
        )
        
        # Create distilled dataset
        distilled_dataset = DistilledDataset(
            original_data_size=1048576,
            distilled_data_size=262144,
            compression_ratio=0.25,
            failure_focus_areas=["clock_domain_crossing"],
            data_path="/path/to/distilled_data.json"
        )
        
        # Create reflection insights
        reflection_insights = ReflectionInsights(
            hypotheses=["Clock domain crossing violation"],
            likely_failure_points=["CDC_FF_inst"],
            recommended_probes=["CDC_FF_inst.Q"],
            confidence_score=0.85,
            analysis_notes="High confidence in clock domain crossing issue"
        )
        
        result = ResultMessage(
            task_id=sample_task_id,
            correlation_id=sample_correlation_id,
            status=TaskStatus.SUCCESS,
            log_output="Analysis pipeline completed",
            analysis_metadata=analysis_metadata,
            distilled_dataset=distilled_dataset,
            reflection_insights=reflection_insights
        )
        
        assert result.analysis_metadata == analysis_metadata
        assert result.distilled_dataset == distilled_dataset
        assert result.reflection_insights == reflection_insights
        assert result.analysis_metadata.stage == "reflect"
        assert result.distilled_dataset.compression_ratio == 0.25
        assert result.reflection_insights.confidence_score == 0.85


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
