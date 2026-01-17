"""
Test Docker Compose setup and RabbitMQ service health.
"""
import subprocess
import time
import requests
import pytest


class TestDockerSetup:
    """Test Docker Compose configuration and service startup."""
    
    def test_docker_compose_file_exists(self):
        """Test that docker-compose.yml exists and is valid."""
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        docker_compose_file = project_root / "infrastructure" / "docker-compose.yml"
        
        assert docker_compose_file.exists(), "docker-compose.yml file not found"
        
        # Test that the file is valid YAML by parsing it
        import yaml
        with open(docker_compose_file, 'r') as f:
            compose_config = yaml.safe_load(f)
        
        # Verify required services
        assert 'services' in compose_config
        assert 'rabbitmq' in compose_config['services']
        assert 'app' in compose_config['services']
        
        # Verify RabbitMQ service configuration
        rabbitmq_service = compose_config['services']['rabbitmq']
        assert rabbitmq_service['image'] == 'rabbitmq:3.11-management-alpine'
        assert '5672:5672' in rabbitmq_service['ports']
        assert '15672:15672' in rabbitmq_service['ports']

        # Verify app service configuration (pinned toolchain)
        app_service = compose_config['services']['app']
        assert 'build' in app_service
        build_config = app_service['build']
        assert build_config['context'] == '..'
        assert build_config['dockerfile'] == 'Dockerfile'
        build_args = build_config.get('args', {})
        assert str(build_args.get('VERILATOR_VERSION')) == '5.044'
        assert app_service.get('command') == ['sleep', 'infinity']

        app_volumes = app_service.get('volumes', [])
        assert '..:/workspace' in app_volumes
        assert 'poetry-cache:/root/.cache/pypoetry' in app_volumes
        assert 'pip-cache:/root/.cache/pip' in app_volumes

        compose_volumes = compose_config.get('volumes', {})
        assert 'poetry-cache' in compose_volumes
        assert 'pip-cache' in compose_volumes

        # Verify Dockerfile exists and pins Verilator version
        dockerfile = project_root / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile not found"
        dockerfile_text = dockerfile.read_text()
        assert "ARG VERILATOR_VERSION=5.044" in dockerfile_text
        assert "iverilog" in dockerfile_text
    
    def test_rabbitmq_definitions_file_exists(self):
        """Test that rabbitmq-definitions.json exists and is valid."""
        from pathlib import Path
        import json
        
        project_root = Path(__file__).parent.parent.parent
        definitions_file = project_root / "infrastructure" / "rabbitmq-definitions.json"
        
        assert definitions_file.exists(), "rabbitmq-definitions.json file not found"
        
        # Test that the file is valid JSON
        with open(definitions_file, 'r') as f:
            definitions = json.load(f)
        
        # Verify required structure
        assert 'queues' in definitions
        assert 'exchanges' in definitions
        assert 'bindings' in definitions
        
        # Verify expected queues exist
        queue_names = [q['name'] for q in definitions['queues']]
        expected_queues = ['agent_tasks', 'process_tasks', 'simulation_tasks', 'dead_letter_queue']
        for queue in expected_queues:
            assert queue in queue_names, f"Expected queue '{queue}' not found in definitions"
    
    def test_management_ui_accessible(self, rabbitmq_service):
        """Test that RabbitMQ Management UI is accessible."""
        # Wait a bit for the UI to be ready
        time.sleep(5)
        
        try:
            response = requests.get('http://localhost:15672', timeout=10)
            assert response.status_code == 200, f"Management UI not accessible: {response.status_code}"
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Failed to access Management UI: {e}")
    
    def test_amqp_connection(self, rabbitmq_connection):
        """Test that AMQP connection works."""
        # The connection fixture already tests this, but let's be explicit
        assert rabbitmq_connection.is_open, "AMQP connection is not open"
        
        # Test that we can create a channel
        channel = rabbitmq_connection.channel()
        assert channel is not None, "Failed to create AMQP channel"
        channel.close()
    
    def test_service_health(self, rabbitmq_channel):
        """Test that RabbitMQ service is healthy and responsive."""
        # Test basic channel operations
        assert rabbitmq_channel.is_open, "Channel is not open"
        
        # Test that we can declare a temporary queue (basic operation)
        result = rabbitmq_channel.queue_declare(queue='test_health_check', durable=False, auto_delete=True)
        assert result is not None, "Failed to declare test queue"
        
        # Clean up
        rabbitmq_channel.queue_delete(queue='test_health_check')
