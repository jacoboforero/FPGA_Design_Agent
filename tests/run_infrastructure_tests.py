#!/usr/bin/env python3
"""
Infrastructure test runner for RabbitMQ setup.

This script runs comprehensive tests to ensure the RabbitMQ infrastructure
is properly configured and integrates correctly with the existing schemas.
"""
import subprocess
import sys
from pathlib import Path


def run_infrastructure_tests():
    """Run all infrastructure tests."""
    print("🧪 Running RabbitMQ Infrastructure Tests")
    print("=" * 50)
    
    # Change to project root directory (go up one level from tests/)
    project_root = Path(__file__).parent.parent
    print(f"📁 Project root: {project_root}")
    
    # Run the tests
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/infrastructure/", 
            "-v", 
            "--tb=short",
            "--color=yes"
        ], cwd=project_root, check=True)
        
        print("\n✅ All infrastructure tests passed!")
        print("\n🎯 Infrastructure Status:")
        print("  • RabbitMQ service: ✅ Ready")
        print("  • Queue configuration: ✅ Valid")
        print("  • Schema integration: ✅ Compatible")
        print("  • Message flow: ✅ Working")
        print("  • DLQ functionality: ✅ Operational")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Infrastructure tests failed with exit code {e.returncode}")
        print("\n🔧 Troubleshooting:")
        print("  1. Ensure Docker is running")
        print("  2. Check that ports 5672 and 15672 are available")
        print("  3. Install dependencies: pip install pika requests pyyaml")
        print("  4. Run individual test files to isolate issues")
        return False


def run_quick_health_check():
    """Run a quick health check without full test suite."""
    print("🏥 Running Quick Health Check")
    print("=" * 30)
    
    # Change to project root directory (go up one level from tests/)
    project_root = Path(__file__).parent.parent
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/infrastructure/test_docker_setup.py::TestDockerSetup::test_amqp_connection",
            "-v"
        ], cwd=project_root, check=True, capture_output=True, text=True)
        
        print("✅ Quick health check passed!")
        return True
        
    except subprocess.CalledProcessError:
        print("❌ Quick health check failed")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        success = run_quick_health_check()
    else:
        success = run_infrastructure_tests()
    
    sys.exit(0 if success else 1)





