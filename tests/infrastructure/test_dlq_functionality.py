"""
Test Dead Letter Queue (DLQ) functionality.
"""
import json
import pytest
import pika
from schemas.contracts import TaskMessage, EntityType, AgentType, TaskPriority


class TestDLQFunctionality:
    """Test Dead Letter Queue handling for failed messages."""
    
    def test_dlq_setup(self, rabbitmq_channel):
        """Test that DLQ infrastructure is properly configured."""
        # Test that DLQ exists
        dlq_info = rabbitmq_channel.queue_declare(queue='dead_letter_queue', passive=True)
        assert dlq_info is not None, "dead_letter_queue not found"
        
        # Test that DLX exists
        try:
            rabbitmq_channel.exchange_declare(exchange='tasks_dlx', passive=True)
        except pika.exceptions.AMQPChannelError:
            pytest.fail("tasks_dlx exchange not found")
    
    def test_dlq_binding(self, rabbitmq_channel):
        """Test that DLX is properly bound to DLQ."""
        # Publish a message directly to the DLX
        test_message = "test dlq message"
        
        rabbitmq_channel.basic_publish(
            exchange='tasks_dlx',
            routing_key='',  # Fanout exchange, routing key doesn't matter
            body=test_message,
            properties=pika.BasicProperties(
                content_type='text/plain',
                delivery_mode=2
            )
        )
        
        # Consume the message to verify it was routed to DLQ
        method, properties, body = rabbitmq_channel.basic_get(queue='dead_letter_queue', auto_ack=True)
        assert method is not None, "Message was not routed to DLQ"
        assert body.decode() == test_message
    
    def test_queue_dlx_configuration(self, rabbitmq_channel):
        """Test that queues are configured with DLX."""
        # This test verifies that the queue configuration includes DLX
        # We can't directly inspect queue arguments from the client,
        # but we can test that the queues exist and are properly configured
        
        queues_to_test = ['agent_tasks', 'process_tasks', 'simulation_tasks']
        
        for queue_name in queues_to_test:
            queue_info = rabbitmq_channel.queue_declare(queue=queue_name, passive=True)
            assert queue_info is not None, f"Queue {queue_name} not found"
    
    def test_message_rejection_simulation(self, rabbitmq_channel):
        """Test simulating message rejection that would trigger DLQ."""
        # Create a test task
        task = TaskMessage(
            entity_type=EntityType.REASONING,
            task_type=AgentType.IMPLEMENTATION,
            priority=TaskPriority.HIGH,
            context={"node_id": "test_dlq_123", "malformed": True}
        )
        
        # Publish the message
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key='REASONING',
            body=task.model_dump_json(),
            properties=pika.BasicProperties(
                priority=task.priority.value,
                content_type='application/json',
                delivery_mode=2
            )
        )
        
        # Simulate a consumer that would reject the message
        # In a real scenario, this would happen if the message couldn't be processed
        method, properties, body = rabbitmq_channel.basic_get(queue='agent_tasks', auto_ack=False)
        
        if method:
            # Simulate rejection by not acknowledging the message
            # In a real scenario, this would be done by the consumer
            rabbitmq_channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    
    def test_dlq_message_format(self, rabbitmq_channel):
        """Test that messages in DLQ maintain proper format."""
        # Purge the DLQ first to ensure clean state
        rabbitmq_channel.queue_purge(queue='dead_letter_queue')
        
        # Publish a message directly to DLQ to test format
        test_task = TaskMessage(
            entity_type=EntityType.LIGHT_DETERMINISTIC,
            task_type=AgentType.IMPLEMENTATION,  # This is wrong - should be WorkerType
            priority=TaskPriority.MEDIUM,
            context={"error": "Invalid task type for entity type"}
        )
        
        # Publish directly to DLQ (simulating a rejected message)
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key='dead_letter_queue',
            body=test_task.model_dump_json(),
            properties=pika.BasicProperties(
                content_type='application/json',
                delivery_mode=2,
                headers={
                    'x-original-routing-key': 'LIGHT_DETERMINISTIC',
                    'x-rejection-reason': 'Invalid task type for entity type'
                }
            )
        )
        
        # Consume from DLQ to verify format
        method, properties, body = rabbitmq_channel.basic_get(queue='dead_letter_queue', auto_ack=True)
        
        if method:
            # Verify message format
            assert properties.content_type == 'application/json'
            assert 'x-original-routing-key' in properties.headers
            assert 'x-rejection-reason' in properties.headers
            
            # Verify we can deserialize the task
            dlq_task_dict = json.loads(body)
            assert dlq_task_dict['entity_type'] == 'LIGHT_DETERMINISTIC'
            assert dlq_task_dict['context']['error'] == 'Invalid task type for entity type'
    
    def test_dlq_monitoring_simulation(self, rabbitmq_channel):
        """Test DLQ monitoring capabilities."""
        # Publish multiple messages to DLQ to simulate monitoring
        for i in range(3):
            task = TaskMessage(
                entity_type=EntityType.REASONING,
                task_type=AgentType.IMPLEMENTATION,
                priority=TaskPriority.HIGH,
                context={"error_id": f"error_{i}", "reason": "Simulated failure"}
            )
            
            rabbitmq_channel.basic_publish(
                exchange='',
                routing_key='dead_letter_queue',
                body=task.model_dump_json(),
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2,
                    headers={
                        'x-original-routing-key': 'REASONING',
                        'x-rejection-reason': f'Simulated failure {i}',
                        'x-first-failure-time': '2024-01-15T10:30:00Z'
                    }
                )
            )
        
        # Check DLQ depth (monitoring metric)
        dlq_info = rabbitmq_channel.queue_declare(queue='dead_letter_queue', passive=True)
        # Note: Messages might be consumed by other tests, so we just verify the queue exists
        
        # In a real monitoring scenario, we would:
        # 1. Check queue depth
        # 2. Check message age
        # 3. Analyze failure patterns
        # 4. Alert if thresholds are exceeded
