#!/usr/bin/env python3
"""
Test runner script for the multi-agent hardware design schemas.
"""
import subprocess
import sys
from pathlib import Path


def main():
    """Run the test suite with coverage reporting."""
    # Change to project root directory (go up one level from tests/)
    project_root = Path(__file__).parent.parent
    
    print("🧪 Running schema tests for multi-agent hardware design system...")
    print("=" * 60)
    
    # Run tests with coverage
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/", 
        "-v", 
        "--cov=schemas", 
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=True)
        print("\n✅ All tests passed!")
        print("📊 Coverage report generated in htmlcov/")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Tests failed with exit code {e.returncode}")
        return e.returncode
    except FileNotFoundError:
        print("❌ pytest not found. Please install test dependencies:")
        print("   pip install pytest pytest-cov pytest-mock")
        return 1


if __name__ == "__main__":
    sys.exit(main())





