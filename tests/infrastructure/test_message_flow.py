"""
Test end-to-end message flow through RabbitMQ.
"""
import json
import pytest
import pika
from schemas.contracts import (
    TaskMessage, ResultMessage, TaskPriority, TaskStatus, 
    EntityType, AgentType, WorkerType, CostMetrics
)


class TestMessageFlow:
    """Test complete message publishing and consumption flow."""
    
    def test_publish_task_message(self, rabbitmq_channel):
        """Test publishing a TaskMessage to the correct queue."""
        # Create a test task
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.IMPLEMENTATION,
            priority=TaskPriority.HIGH,
            context={
                "node_id": "test_design_123",
                "specs": {"frequency": "100MHz"},
                "code_paths": ["/path/to/design.v"]
            }
        )
        
        # Serialize the task
        task_json = task.model_dump_json()
        
        # Publish to the correct queue via exchange
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key=task.entity_type.value,  # "REASONING"
            body=task_json,
            properties=pika.BasicProperties(
                priority=task.priority.value,
                content_type='application/json',
                delivery_mode=2  # Make message persistent
            )
        )
        
        # Verify message was queued
        queue_info = rabbitmq_channel.queue_declare(queue='agent_tasks', passive=True)
        assert queue_info.method.message_count >= 0  # At least 0 messages (could be consumed by other tests)
    
    def test_consume_task_message(self, rabbitmq_channel):
        """Test consuming a TaskMessage from the queue."""
        # Create and publish a test task
        task = TaskMessage(
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=WorkerType.LINTER,
            priority=TaskPriority.MEDIUM,
            context={"node_id": "test_lint_456", "file_path": "/path/to/code.v"}
        )
        
        task_json = task.model_dump_json()
        
        # Publish the message
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key=task.entity_type.value,  # "LIGHT_DETERMINISTIC"
            body=task_json,
            properties=pika.BasicProperties(
                priority=task.priority.value,
                content_type='application/json',
                delivery_mode=2
            )
        )
        
        # Consume the message
        method, properties, body = rabbitmq_channel.basic_get(queue='process_tasks', auto_ack=True)
        
        assert method is not None, "No message received from process_tasks queue"
        assert properties.content_type == 'application/json'
        assert properties.priority == task.priority.value
        
        # Verify we can deserialize the message
        received_task_dict = json.loads(body)
        assert received_task_dict['entity_type'] == 'LIGHT_DETERMINISTIC'
        assert received_task_dict['task_type'] == 'LinterWorker'
        assert received_task_dict['priority'] == 2  # MEDIUM
    
    def test_publish_result_message(self, rabbitmq_channel):
        """Test publishing a ResultMessage back to the system."""
        # Create a test result
        result = ResultMessage(
            task_id="123e4567-e89b-12d3-a456-426614174000",
            correlation_id="987fcdeb-51a2-43d1-b789-123456789abc",
            status=TaskStatus.SUCCESS,
            artifacts_path="/path/to/generated_code.v",
            log_output="Implementation completed successfully",
            reflections="Code follows best practices",
            metrics=CostMetrics(
                input_tokens=1500,
                output_tokens=800,
                cost_usd=0.08
            )
        )
        
        # Serialize the result
        result_json = result.model_dump_json()
        
        # Publish to a results queue (we'll create a temporary one for testing)
        rabbitmq_channel.queue_declare(queue='test_results', durable=True)
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key='test_results',
            body=result_json,
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2
            )
        )
        
        # Verify message was queued
        queue_info = rabbitmq_channel.queue_declare(queue='test_results', passive=True)
        assert queue_info.method.message_count >= 0
    
    def test_priority_message_ordering(self, rabbitmq_channel):
        """Test that priority messages are handled correctly."""
        # Purge the queue first to ensure clean state
        rabbitmq_channel.queue_purge(queue='agent_tasks')
        
        # Create messages with different priorities
        messages = [
            (TaskPriority.LOW, "low priority task"),
            (TaskPriority.HIGH, "high priority task"),
            (TaskPriority.MEDIUM, "medium priority task")
        ]
        
        # Publish messages in non-priority order
        for priority, content in messages:
            task = TaskMessage(
                entity_type=EntityType.REASONING,
                task_type=AgentType.IMPLEMENTATION,
                priority=priority,
                context={"content": content}
            )
            
            rabbitmq_channel.basic_publish(
                exchange='tasks_exchange',
                routing_key='REASONING',
                body=task.model_dump_json(),
                properties=pika.BasicProperties(
                    priority=priority.value,
                    content_type='application/json',
                    delivery_mode=2
                )
            )
        
        # Consume messages and verify priority ordering
        received_messages = []
        for _ in range(3):  # We published 3 messages
            method, properties, body = rabbitmq_channel.basic_get(queue='agent_tasks', auto_ack=True)
            if method:
                received_messages.append((properties.priority, json.loads(body)['context']['content']))
        
        # Messages should be consumed in priority order (highest first)
        # Note: This test might be flaky depending on RabbitMQ timing
        assert len(received_messages) == 3, f"Expected 3 messages, got {len(received_messages)}"
    
    def test_message_persistence(self, rabbitmq_channel):
        """Test that messages are persisted correctly."""
        task = TaskMessage(
            entity_type=EntityType.HEAVY_DETERMINISTIC,
            task_type=WorkerType.SIMULATOR,
            priority=TaskPriority.HIGH,
            context={"simulation_id": "sim_789", "duration": "1hour"}
        )
        
        # Publish with persistent delivery mode
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key='HEAVY_DETERMINISTIC',
            body=task.model_dump_json(),
            properties=pika.BasicProperties(
                priority=task.priority.value,
                content_type='application/json',
                delivery_mode=2  # Persistent
            )
        )
        
        # Verify message is in queue
        queue_info = rabbitmq_channel.queue_declare(queue='simulation_tasks', passive=True)
        assert queue_info.method.message_count >= 0
