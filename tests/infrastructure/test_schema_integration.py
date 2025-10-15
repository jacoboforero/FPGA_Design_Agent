"""
Test integration between schemas and RabbitMQ configuration.
"""
import json
import pytest
import pika
from schemas.contracts import (
    TaskMessage, ResultMessage, TaskPriority, TaskStatus, 
    EntityType, AgentType, WorkerType, CostMetrics
)


class TestSchemaIntegration:
    """Test that schemas integrate properly with RabbitMQ setup."""
    
    def test_entity_type_routing_alignment(self):
        """Test that EntityType enum values align with routing keys."""
        # These should match the routing keys in rabbitmq-definitions.json
        expected_routing_keys = {
            EntityType.REASONING.value: "REASONING",
            EntityType.LIGHT_DETERMINISTIC.value: "LIGHT_DETERMINISTIC", 
            EntityType.HEAVY_DETERMINISTIC.value: "HEAVY_DETERMINISTIC"
        }
        
        for entity_type, routing_key in expected_routing_keys.items():
            assert entity_type == routing_key, f"EntityType {entity_type} doesn't match routing key {routing_key}"
    
    def test_priority_enum_alignment(self):
        """Test that TaskPriority enum aligns with RabbitMQ priority levels."""
        # RabbitMQ supports priorities 0-255, we use 1-3
        assert TaskPriority.LOW.value == 1
        assert TaskPriority.MEDIUM.value == 2  
        assert TaskPriority.HIGH.value == 3
        
        # All values should be within valid range
        for priority in TaskPriority:
            assert 1 <= priority.value <= 3, f"Priority {priority.value} outside valid range"
    
    def test_task_message_serialization(self):
        """Test that TaskMessage can be serialized for RabbitMQ."""
        # Create a test task message
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.IMPLEMENTATION,
            priority=TaskPriority.HIGH,
            context={
                "node_id": "test_design_123",
                "specs": {"frequency": "100MHz", "area": "1000um2"},
                "code_paths": ["/path/to/design.v"]
            }
        )
        
        # Test JSON serialization (what we'd send to RabbitMQ)
        task_json = task.model_dump_json()
        assert isinstance(task_json, str)
        
        # Test that we can deserialize it back
        task_dict = json.loads(task_json)
        assert task_dict['entity_type'] == 'REASONING'
        assert task_dict['task_type'] == 'ImplementationAgent'
        assert task_dict['priority'] == 3  # HIGH priority
    
    def test_result_message_serialization(self):
        """Test that ResultMessage can be serialized for RabbitMQ."""
        # Create a test result message
        result = ResultMessage(
            task_id="123e4567-e89b-12d3-a456-426614174000",
            correlation_id="987fcdeb-51a2-43d1-b789-123456789abc",
            status=TaskStatus.SUCCESS,
            artifacts_path="/path/to/generated_code.v",
            log_output="Task completed successfully. Generated 150 lines of Verilog.",
            reflections="The implementation follows best practices for clock domain crossing.",
            metrics=CostMetrics(
                input_tokens=2000,
                output_tokens=1000,
                cost_usd=0.10
            )
        )
        
        # Test JSON serialization
        result_json = result.model_dump_json()
        assert isinstance(result_json, str)
        
        # Test that we can deserialize it back
        result_dict = json.loads(result_json)
        assert result_dict['status'] == 'SUCCESS'
        assert result_dict['metrics']['cost_usd'] == 0.10
    
    def test_routing_key_generation(self):
        """Test that we can generate correct routing keys from TaskMessage."""
        # Test REASONING entity
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.IMPLEMENTATION,
            context={"test": "data"}
        )
        routing_key = task.entity_type.value
        assert routing_key == "REASONING"
        
        # Test LIGHT_DETERMINISTIC entity
        task = TaskMessage(
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=WorkerType.LINTER,
            context={"test": "data"}
        )
        routing_key = task.entity_type.value
        assert routing_key == "LIGHT_DETERMINISTIC"
        
        # Test HEAVY_DETERMINISTIC entity
        task = TaskMessage(
            entity_type=EntityType.HEAVY_DETERMINISTIC,
            task_type=WorkerType.SIMULATOR,
            context={"test": "data"}
        )
        routing_key = task.entity_type.value
        assert routing_key == "HEAVY_DETERMINISTIC"
    
    def test_priority_mapping(self):
        """Test that TaskPriority maps correctly to RabbitMQ priorities."""
        priority_mapping = {
            TaskPriority.LOW: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.HIGH: 3
        }
        
        for task_priority, rabbitmq_priority in priority_mapping.items():
            assert task_priority.value == rabbitmq_priority, f"Priority mapping mismatch: {task_priority} -> {rabbitmq_priority}"
    
    def test_queue_selection_logic(self):
        """Test logic for selecting the correct queue based on EntityType."""
        def get_queue_name(entity_type: EntityType) -> str:
            """Helper function to determine queue name from entity type."""
            if entity_type == EntityType.REASONING:
                return "agent_tasks"
            elif entity_type == EntityType.LIGHT_DETERMINISTIC:
                return "process_tasks"
            elif entity_type == EntityType.HEAVY_DETERMINISTIC:
                return "simulation_tasks"
            else:
                raise ValueError(f"Unknown entity type: {entity_type}")
        
        # Test each entity type
        assert get_queue_name(EntityType.REASONING) == "agent_tasks"
        assert get_queue_name(EntityType.LIGHT_DETERMINISTIC) == "process_tasks"
        assert get_queue_name(EntityType.HEAVY_DETERMINISTIC) == "simulation_tasks"
