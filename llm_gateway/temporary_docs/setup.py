

# =============================================================================
# setup.py
"""
Setup script for LLM Gateway package.

Install with: pip install -e .
Or for development: pip install -e ".[dev]"
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="llm-gateway",
    version="0.1.0",
    description="Unified interface for multiple LLM providers with transport abstraction",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/llm-gateway",
    packages=find_packages(exclude=["tests", "examples"]),
    python_requires=">=3.9",
    install_requires=[
        "pydantic>=2.0.0",
        "httpx>=0.24.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
        ],
        "openai": [
            "openai>=1.0.0",
        ],
        "anthropic": [
            "anthropic>=0.25.0",
        ],
        "all": [
            "openai>=1.0.0",
            "anthropic>=0.25.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)