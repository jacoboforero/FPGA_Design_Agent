#!/bin/bash
# Quick Start Script for Enhanced run_local_spec.py
# This demonstrates how to run the full pipeline

set -e

echo "====================================================================="
echo "Enhanced run_local_spec.py - Full Pipeline Demo"
echo "====================================================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check if RabbitMQ is running
if ! nc -z localhost 5672 2>/dev/null; then
    echo "❌ RabbitMQ is not running on localhost:5672"
    echo "   Please start it with: cd infrastructure && docker-compose up -d"
    exit 1
fi
echo "✓ RabbitMQ is running"

# Check if iverilog is installed
if ! command -v iverilog &> /dev/null; then
    echo "❌ iverilog is not installed"
    echo "   Please install it: https://github.com/steveicarus/iverilog"
    exit 1
fi
echo "✓ iverilog is installed"

# Check environment variables
if [ -z "$USE_LLM" ]; then
    echo "⚠️  USE_LLM not set, setting to 1"
    export USE_LLM=1
fi

if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ No LLM API key set"
    echo "   Please set OPENAI_API_KEY or ANTHROPIC_API_KEY"
    exit 1
fi
echo "✓ LLM API key configured"

echo ""
echo "====================================================================="
echo "Running Examples"
echo "====================================================================="
echo ""

# Example 1: Single spec file - spec generation only
echo "Example 1: Generate spec only (no orchestrator)"
echo "---------------------------------------------------------------------"
PYTHONPATH=. python3 scripts/run_local_spec.py \
    --spec-file processed_prompts/Prob001_zero.txt
echo ""

# Example 2: Single spec file - full pipeline
echo "Example 2: Full pipeline for single problem"
echo "---------------------------------------------------------------------"
PYTHONPATH=. python3 scripts/run_local_spec.py \
    --spec-file processed_prompts/Prob001_zero.txt \
    --full \
    --timeout 180
echo ""

# Example 3: Batch mode - first 3 problems - spec only
echo "Example 3: Batch spec generation (3 problems)"
echo "---------------------------------------------------------------------"
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 3
echo ""

# Example 4: Batch mode - first 3 problems - full pipeline
echo "Example 4: Batch full pipeline (3 problems)"
echo "---------------------------------------------------------------------"
PYTHONPATH=. python3 scripts/run_local_spec.py \
    --batch 3 \
    --full \
    --timeout 180
echo ""

echo "====================================================================="
echo "Demo Complete!"
echo "====================================================================="
echo ""
echo "Results are stored in:"
echo "  - Specs: artifacts/task_memory/specs/"
echo "  - Generated RTL: artifacts/generated/rtl/"
echo "  - Test logs: artifacts/verilog_eval_tests/"
echo ""
