# Enhanced run_local_spec.py - Implementation Summary

## Overview
Enhanced `scripts/run_local_spec.py` to support full end-to-end pipeline execution, integrating:
1. Spec generation (existing)
2. Orchestrator execution (NEW)
3. Verilog evaluation testing (NEW)

## Key Changes

### 1. New Imports and Constants
```python
import pika
import json
import subprocess
import threading
import shutil
import os

from apps.cli.cli import connection_params_from_env, start_workers, stop_workers
from orchestrator.orchestrator_service import DemoOrchestrator
from agents.planner.worker import PlannerWorker
from core.schemas.contracts import AgentType, EntityType, ResultMessage, TaskMessage, TaskStatus
```

### 2. New Functions

#### `_run_planner_task(params, timeout=60.0)`
- Submits planner task to RabbitMQ
- Waits for planner to generate design context and DAG
- Returns when planning completes or times out

#### `_clean_artifacts()`
- Cleans previous generation artifacts
- Prepares clean slate for new runs

#### `_run_orchestrator(params, timeout=180.0)`
- Starts all worker pools (implementation, testbench, lint, sim, etc.)
- Runs planner worker
- Executes orchestrator to drive multi-agent workflow
- Returns RTL path and design context

#### `_find_verilog_eval_files(prob_name)`
- Locates test and reference files for a problem
- Matches `Prob001_zero` → `Prob001_zero_test.sv` and `Prob001_zero_ref.sv`
- Returns file paths for testing

#### `_run_verilog_eval_test(generated_rtl, prob_name)`
- Compiles generated Verilog with iverilog
- Runs test bench simulation
- Checks for "Mismatches: 0" in output
- Returns pass/fail result with logs

### 3. Enhanced Core Functions

#### `_run_single_spec()` - Enhanced
**New Parameters:**
- `run_full_pipeline: bool = False` - Enable full workflow
- `timeout: float = 180.0` - Orchestrator timeout

**New Behavior:**
- When `run_full_pipeline=True`:
  1. Generates spec (existing)
  2. Checks RabbitMQ connection
  3. Runs orchestrator to generate Verilog
  4. Runs verilog_eval test
  5. Reports PASS/FAIL

**Returns:** Dictionary with:
```python
{
    "spec_path": str,
    "module_name": str,
    "spec_artifacts": str,
    "rtl_path": Path,  # if full pipeline
    "design_context": dict,  # if full pipeline
    "test": {  # if full pipeline
        "passed": bool,
        "compile_log": str,
        "test_log": str,
        "error": str  # if failed
    }
}
```

#### `_run_batch()` - Enhanced
**New Parameters:**
- `run_full_pipeline: bool = False`
- `timeout: float = 180.0`

**New Behavior:**
- Processes each problem through full pipeline if enabled
- Collects pass/fail statistics
- Prints summary with pass rate

### 4. Enhanced CLI Arguments

#### New Arguments
- `--full` - Run full pipeline mode
- `--timeout SECONDS` - Set orchestrator timeout (default: 180)

#### Updated Help Text
```
Generate spec artifacts and optionally run full pipeline with verilog_eval testing.
```

## Usage Examples

### Spec Generation Only (Original)
```bash
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 10
```

### Full Pipeline (New)
```bash
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 10 --full
```

### Single Problem - Full Pipeline
```bash
PYTHONPATH=. python3 scripts/run_local_spec.py \
    --spec-file processed_prompts/Prob001_zero.txt \
    --full \
    --timeout 180
```

## Output Format

### Full Pipeline Output
```
================================================================================
Processing Prob001_zero.txt
================================================================================
Generating initial checklist from spec text...
Drafting missing field: L1.description
...
✓ Wrote spec artifacts for module 'zero' from Prob001_zero.txt
Cleaned artifact directory
✓ Planner completed successfully
Running orchestrator to generate Verilog...
✓ Orchestrator generated RTL: artifacts/generated/rtl/zero.sv
Running verilog_eval test for Prob001_zero...
✓ PASS: Prob001_zero

================================================================================
SUMMARY
================================================================================

Pass rate: 8/10 (80.0%)
  PASS: Prob001_zero
  PASS: Prob002_m2014_q4i
  FAIL: Prob003_step_one
  ...
```

## Architecture Integration

The enhanced script bridges three major subsystems:

```
processed_prompts/
    ↓
[Spec Helper Agent] → specs
    ↓
[Planner Agent] → Design Context + DAG
    ↓
[Orchestrator + Workers] → Verilog RTL
    ↓
[Verilog Eval + Iverilog] → PASS/FAIL
```

## Files Created/Modified

### Modified
- `scripts/run_local_spec.py` - Enhanced with orchestrator and testing

### New
- `scripts/README_run_local_spec.md` - Comprehensive documentation
- `scripts/demo_run_local_spec.sh` - Linux demo script
- `scripts/demo_run_local_spec.bat` - Windows demo script

## Testing Strategy

### Unit Testing
Each function can be tested independently:
- `_run_planner_task()` - Test planning workflow
- `_find_verilog_eval_files()` - Test file matching
- `_run_verilog_eval_test()` - Test evaluation harness

### Integration Testing
Use batch mode with small counts:
```bash
PYTHONPATH=. python3 scripts/run_local_spec.py --batch 3 --full
```

### Smoke Testing
Run demo scripts:
```bash
bash scripts/demo_run_local_spec.sh
# or on Windows
scripts\demo_run_local_spec.bat
```

## Performance Characteristics

### Spec-Only Mode
- **Time:** ~10-30s per problem (LLM-dependent)
- **Resources:** Minimal (LLM API calls only)

### Full Pipeline Mode
- **Time:** ~60-180s per problem
- **Resources:**
  - RabbitMQ connection
  - Worker pool (6+ workers)
  - LLM API calls
  - Iverilog compilation + simulation

### Scalability
- Sequential execution (no parallelism yet)
- Memory-safe (cleans artifacts between runs)
- Suitable for batch evaluation up to ~100 problems

## Future Enhancements

### Possible Improvements
1. **Parallel execution** - Run multiple problems concurrently
2. **Resume capability** - Skip already-passed problems
3. **Detailed reporting** - Generate CSV/JSON result summaries
4. **Error categorization** - Classify failure modes
5. **Performance profiling** - Track time per stage
6. **Interactive mode** - Allow inspection of failed cases

## Backward Compatibility

✅ **Fully backward compatible**
- Default behavior unchanged (spec generation only)
- New features opt-in via `--full` flag
- All existing scripts continue to work

## Dependencies

### Required at Runtime
- RabbitMQ (for `--full` mode)
- Iverilog (for `--full` mode)
- LLM Gateway configured
- Worker modules (already in repo)

### Python Packages
All dependencies already in `pyproject.toml`:
- pika (RabbitMQ client)
- langchain (LLM gateway)
- All existing agent/worker modules

## Error Handling

### Graceful Degradation
- RabbitMQ check before starting workers
- Timeout protection at each stage
- Comprehensive error messages
- Log files for debugging

### Error Messages
```python
# RabbitMQ unavailable
"RabbitMQ not reachable at amqp://user:password@localhost:5672/"

# Planning failure
"Planning failed: <error details>"

# No test files
"No verilog_eval test files found for Prob001_zero"

# Compilation failure
"Compilation failed" + compile log path

# Timeout
"Test execution timed out"
```

## Conclusion

This enhancement transforms `run_local_spec.py` from a simple spec generation tool into a comprehensive evaluation harness that can:
- Generate formal specifications from natural language
- Execute the full multi-agent design workflow
- Validate generated Verilog against test benches
- Report quantitative pass/fail metrics

This enables end-to-end evaluation of the FPGA Design Agent system on the VerilogEval benchmark.
