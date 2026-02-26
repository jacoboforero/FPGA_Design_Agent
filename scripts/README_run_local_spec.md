# Enhanced run_local_spec.py - Full Pipeline Runner

## Overview

The enhanced `run_local_spec.py` script now supports running the full FPGA design pipeline:

1. **Spec Generation** - Converts processed prompts to formal specifications
2. **Orchestrator Execution** - Runs the multi-agent system to generate Verilog RTL
3. **Verilog Evaluation** - Tests generated Verilog against verilog_eval test benches

## Prerequisites

### Infrastructure Requirements
- RabbitMQ running (for orchestrator mode)
- Iverilog installed (for verilog_eval testing)
- LLM Gateway configured (OpenAI API key or other provider)

### Start Infrastructure

```bash
# In the infrastructure/ directory
docker-compose up -d
```

### Environment Variables

```bash
export USE_LLM=1
export OPENAI_API_KEY=your_api_key_here
# Or configure other LLM providers as needed
```

## Usage

### Mode 1: Spec Generation Only (Original Behavior)

Generate spec artifacts without running the full pipeline:

```bash
# Single spec file
PYTHONPATH=. python3 scripts/run_local_spec.py --spec-file processed_prompts/Prob001_zero.txt

# Batch mode (first 10 problems)
PYTHONPATH=. python3 scripts/run_local_spec.py --batch

# Batch mode (first 20 problems)
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 20
```

### Mode 2: Full Pipeline with Verilog Evaluation (NEW)

Run the complete pipeline including orchestrator and verilog_eval testing:

```bash
# Single spec file - full pipeline
PYTHONPATH=. python3 scripts/run_local_spec.py --spec-file processed_prompts/Prob001_zero.txt --full

# Batch mode - full pipeline (first 10 problems)
PYTHONPATH=. python3 scripts/run_local_spec.py --batch --full

# Batch mode with custom timeout (default 180s per problem)
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 5 --full --timeout 300
```

## Command Line Arguments

- `--spec-file PATH` - Path to a single spec text file
- `--batch [N]` - Run first N problems from processed_prompts/ (default: 10)
- `--full` - Run full pipeline (spec → orchestrator → verilog → verilog_eval test)
- `--timeout SECONDS` - Timeout for orchestrator execution (default: 180)

## What Happens in Full Pipeline Mode

### 1. Spec Generation
- Uses LLM to parse the problem spec
- Generates formal specification artifacts (L1-L5)
- Writes spec files to `artifacts/task_memory/specs/`

### 2. Orchestrator Execution
- Starts worker pool (implementation, testbench, lint, etc.)
- Runs planner agent to create design context and DAG
- Orchestrates multi-agent workflow to generate Verilog
- Output: `artifacts/generated/rtl/<module_name>.sv`

### 3. Verilog Evaluation
- Locates matching test file from `verilog_eval/dataset_spec-to-rtl/`
- Compiles generated Verilog with iverilog alongside test bench
- Runs simulation to verify correctness
- Reports PASS/FAIL based on test results

## Output

### Spec-Only Mode
```
✓ Wrote spec artifacts for module 'zero' from Prob001_zero.txt
```

### Full Pipeline Mode
```
✓ Wrote spec artifacts for module 'zero' from Prob001_zero.txt
Cleaned artifact directory
✓ Planner completed successfully
Running orchestrator to generate Verilog...
✓ Orchestrator generated RTL: artifacts/generated/rtl/zero.sv
Running verilog_eval test for Prob001_zero...
✓ PASS: Prob001_zero
```

### Batch Summary
```
================================================================================
SUMMARY
================================================================================

Pass rate: 8/10 (80.0%)
  PASS: Prob001_zero
  PASS: Prob002_m2014_q4i
  FAIL: Prob003_step_one
  ...
```

## Troubleshooting

### RabbitMQ Connection Error
```
RabbitMQ not reachable at amqp://user:password@localhost:5672/
```
**Solution**: Start infrastructure with `docker-compose up -d` in `infrastructure/`

### LLM Gateway Unavailable
```
LLM gateway unavailable. Set USE_LLM=1 and provider API key(s)
```
**Solution**: 
```bash
export USE_LLM=1
export OPENAI_API_KEY=your_key_here
```

### No Test Files Found
```
No verilog_eval test files found for ProbXXX_name
```
**Solution**: Ensure the problem name matches a test case in `verilog_eval/dataset_spec-to-rtl/`

### Timeout
```
Planner timed out waiting for results
```
**Solution**: Increase timeout with `--timeout 300` or check RabbitMQ/worker logs

## Examples

### Quick Test (Single Problem)
```bash
# Test one problem end-to-end
PYTHONPATH=. python3 scripts/run_local_spec.py \
  --spec-file processed_prompts/Prob001_zero.txt \
  --full \
  --timeout 120
```

### Batch Evaluation (Research Mode)
```bash
# Evaluate first 50 problems for pass rate analysis
PYTHONPATH=. python3 scripts/run_local_spec.py \
  --batch 50 \
  --full \
  --timeout 240
```

### Development Mode (Spec Generation Only)
```bash
# Quick spec generation for debugging
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 5
```

## Performance Notes

- **Spec-only mode**: ~10-30s per problem (LLM-dependent)
- **Full pipeline mode**: ~60-180s per problem (includes orchestration + testing)
- Batch mode processes sequentially (parallel execution not yet implemented)
- Consider increasing `--timeout` for complex designs

## Architecture

The script integrates three major components:

1. **Spec Helper Agent** - Parses natural language specs into formal artifacts
2. **Orchestrator + Workers** - Multi-agent system for Verilog generation
3. **Verilog Eval Harness** - Iverilog-based test execution

This provides an end-to-end evaluation pipeline for comparing LLM-generated specs and RTL against ground truth test benches.
