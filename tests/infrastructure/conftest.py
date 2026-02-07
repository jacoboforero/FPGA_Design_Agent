"""
Infrastructure test fixtures for RabbitMQ testing.
"""
import os
import shutil
import subprocess
import time
import pytest
import pika
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
INFRASTRUCTURE_DIR = PROJECT_ROOT / "infrastructure"


@pytest.fixture(scope="session")
def rabbitmq_service():
    """
    Start RabbitMQ service and ensure it's healthy before tests.
    """
    docker_path = shutil.which("docker")
    compose_path = shutil.which("docker-compose")
    if not docker_path or not compose_path:
        pytest.skip("Docker or docker-compose is not available; skipping infrastructure tests.")

    try:
        subprocess.run(
            [docker_path, "info"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        detail = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
        pytest.skip(f"Docker daemon is unavailable: {detail.strip()}")

    # Change to infrastructure directory
    original_cwd = os.getcwd()
    os.chdir(INFRASTRUCTURE_DIR)
    
    try:
        # Start the service
        print("Starting RabbitMQ service...")
        result = subprocess.run(
            [compose_path, "up", "-d", "rabbitmq"],
            capture_output=True, 
            text=True, 
            check=True
        )
        print(f"Service start result: {result.stdout}")
        
        # Wait for service to be ready (management API)
        print("Waiting for RabbitMQ to be ready...")
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                # Check if management API is up
                import requests
                response = requests.get('http://localhost:15672/api/overview', timeout=2)
                if response.status_code in [200, 401]:  # 401 means server is up but we're not authenticated
                    print("RabbitMQ management API is ready!")
                    break
            except Exception as e:
                if attempt < max_attempts - 1:
                    print(f"Attempt {attempt + 1}: RabbitMQ not ready yet: {e}")
                    time.sleep(2)
                else:
                    raise Exception(f"RabbitMQ failed to start after {max_attempts} attempts")
        
        # Create the user (definitions file doesn't create users when it creates vhost)
        print("Creating RabbitMQ user...")
        try:
            subprocess.run(
                [docker_path, "exec", "multi-agent-task-broker", "rabbitmqctl", "add_user", "user", "password"],
                capture_output=True,
                text=True,
                check=False  # User might already exist
            )
            subprocess.run(
                [docker_path, "exec", "multi-agent-task-broker", "rabbitmqctl", "set_user_tags", "user", "administrator"],
                capture_output=True,
                text=True,
                check=True
            )
            subprocess.run(
                [docker_path, "exec", "multi-agent-task-broker", "rabbitmqctl", "set_permissions", "-p", "/", "user", ".*", ".*", ".*"],
                capture_output=True,
                text=True,
                check=True
            )
            print("User created successfully!")
        except subprocess.CalledProcessError as e:
            print(f"Warning: User creation failed (might already exist): {e}")
        
        # Now test AMQP connection
        print("Testing AMQP connection...")
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host='localhost',
                    port=5672,
                    virtual_host='/',
                    credentials=pika.PlainCredentials('user', 'password')
                )
            )
            connection.close()
            print("AMQP connection successful!")
        except Exception as e:
            raise Exception(f"Failed to connect to RabbitMQ: {e}")
        
        yield "rabbitmq"
        
    finally:
        # Cleanup: stop the service
        print("Stopping RabbitMQ service...")
        subprocess.run(
            [compose_path, "down"], 
            capture_output=True, 
            text=True
        )
        os.chdir(original_cwd)


@pytest.fixture
def rabbitmq_connection(rabbitmq_service):
    """
    Provide a RabbitMQ connection for tests.
    """
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host='localhost',
            port=5672,
            virtual_host='/',
            credentials=pika.PlainCredentials('user', 'password')
        )
    )
    yield connection
    connection.close()


@pytest.fixture
def rabbitmq_channel(rabbitmq_connection):
    """
    Provide a RabbitMQ channel for tests.
    """
    channel = rabbitmq_connection.channel()
    yield channel
    channel.close()
