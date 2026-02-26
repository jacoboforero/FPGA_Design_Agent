@echo off
REM Quick Start Script for Enhanced run_local_spec.py (Windows)
REM This demonstrates how to run the full pipeline

echo =====================================================================
echo Enhanced run_local_spec.py - Full Pipeline Demo
echo =====================================================================
echo.

echo Checking prerequisites...

REM Check if RabbitMQ is running
powershell -Command "Test-NetConnection -ComputerName localhost -Port 5672 -InformationLevel Quiet" >nul 2>&1
if %errorlevel% neq 0 (
    echo X RabbitMQ is not running on localhost:5672
    echo    Please start it with: cd infrastructure ^&^& docker-compose up -d
    exit /b 1
)
echo + RabbitMQ is running

REM Check if iverilog is installed
where iverilog >nul 2>&1
if %errorlevel% neq 0 (
    echo X iverilog is not installed
    echo    Please install it: https://github.com/steveicarus/iverilog
    exit /b 1
)
echo + iverilog is installed

REM Check environment variables
if not defined USE_LLM (
    echo ! USE_LLM not set, setting to 1
    set USE_LLM=1
)

if not defined OPENAI_API_KEY (
    if not defined ANTHROPIC_API_KEY (
        echo X No LLM API key set
        echo    Please set OPENAI_API_KEY or ANTHROPIC_API_KEY
        exit /b 1
    )
)
echo + LLM API key configured

echo.
echo =====================================================================
echo Running Examples
echo =====================================================================
echo.

REM Example 1: Single spec file - spec generation only
echo Example 1: Generate spec only (no orchestrator)
echo ---------------------------------------------------------------------
set PYTHONPATH=.
python scripts\run_local_spec.py --spec-file processed_prompts\Prob001_zero.txt
echo.

REM Example 2: Single spec file - full pipeline
echo Example 2: Full pipeline for single problem
echo ---------------------------------------------------------------------
python scripts\run_local_spec.py --spec-file processed_prompts\Prob001_zero.txt --full --timeout 180
echo.

REM Example 3: Batch mode - first 3 problems - spec only
echo Example 3: Batch spec generation (3 problems)
echo ---------------------------------------------------------------------
python scripts\run_local_spec.py --batch 3
echo.

REM Example 4: Batch mode - first 3 problems - full pipeline
echo Example 4: Batch full pipeline (3 problems)
echo ---------------------------------------------------------------------
python scripts\run_local_spec.py --batch 3 --full --timeout 180
echo.

echo =====================================================================
echo Demo Complete!
echo =====================================================================
echo.
echo Results are stored in:
echo   - Specs: artifacts\task_memory\specs\
echo   - Generated RTL: artifacts\generated\rtl\
echo   - Test logs: artifacts\verilog_eval_tests\
echo.
