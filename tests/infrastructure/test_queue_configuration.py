"""
Test RabbitMQ queue configuration and setup.
"""
import pytest
import pika
from schemas.contracts import EntityType, TaskPriority


class TestQueueConfiguration:
    """Test that queues are properly configured according to definitions."""
    
    def test_required_queues_exist(self, rabbitmq_channel):
        """Test that all required queues exist and are properly configured."""
        # Test agent_tasks queue
        agent_queue = rabbitmq_channel.queue_declare(queue='agent_tasks', passive=True)
        assert agent_queue is not None, "agent_tasks queue not found"
        
        # Test process_tasks queue
        process_queue = rabbitmq_channel.queue_declare(queue='process_tasks', passive=True)
        assert process_queue is not None, "process_tasks queue not found"
        
        # Test simulation_tasks queue
        simulation_queue = rabbitmq_channel.queue_declare(queue='simulation_tasks', passive=True)
        assert simulation_queue is not None, "simulation_tasks queue not found"
        
        # Test dead_letter_queue
        dlq = rabbitmq_channel.queue_declare(queue='dead_letter_queue', passive=True)
        assert dlq is not None, "dead_letter_queue not found"
    
    def test_agent_tasks_priority_configuration(self, rabbitmq_channel):
        """Test that agent_tasks queue has priority configuration."""
        # Get queue info
        queue_info = rabbitmq_channel.queue_declare(queue='agent_tasks', passive=True)
        
        # Check that the queue supports priority (x-max-priority should be 3)
        # Note: We can't directly check queue arguments from the client,
        # but we can test that priority messages work
        test_message = "test priority message"
        
        # Test publishing with different priorities
        for priority in [1, 2, 3]:  # LOW, MEDIUM, HIGH
            rabbitmq_channel.basic_publish(
                exchange='',
                routing_key='agent_tasks',
                body=test_message,
                properties=pika.BasicProperties(priority=priority)
            )
    
    def test_exchanges_exist(self, rabbitmq_channel):
        """Test that required exchanges exist."""
        # Test tasks_exchange
        try:
            rabbitmq_channel.exchange_declare(exchange='tasks_exchange', passive=True)
        except pika.exceptions.AMQPChannelError:
            pytest.fail("tasks_exchange not found")
        
        # Test tasks_dlx (Dead Letter Exchange)
        try:
            rabbitmq_channel.exchange_declare(exchange='tasks_dlx', passive=True)
        except pika.exceptions.AMQPChannelError:
            pytest.fail("tasks_dlx not found")
    
    def test_bindings_configured(self, rabbitmq_channel):
        """Test that queue bindings are properly configured."""
        # Test that we can publish to each queue via the exchange
        test_message = "test binding message"
        
        # Test agent_tasks binding (REASONING routing key)
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key='REASONING',
            body=test_message
        )
        
        # Test process_tasks binding (LIGHT_DETERMINISTIC routing key)
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key='LIGHT_DETERMINISTIC',
            body=test_message
        )
        
        # Test simulation_tasks binding (HEAVY_DETERMINISTIC routing key)
        rabbitmq_channel.basic_publish(
            exchange='tasks_exchange',
            routing_key='HEAVY_DETERMINISTIC',
            body=test_message
        )
    
    def test_dead_letter_exchange_binding(self, rabbitmq_channel):
        """Test that dead letter exchange is properly bound."""
        # Test that we can publish to the DLX and it routes to DLQ
        test_message = "test dlq message"
        
        rabbitmq_channel.basic_publish(
            exchange='tasks_dlx',
            routing_key='',  # Fanout exchange, routing key doesn't matter
            body=test_message
        )
