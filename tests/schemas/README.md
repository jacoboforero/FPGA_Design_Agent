# Schema Testing Suite

This directory contains comprehensive tests for the multi-agent hardware design system schemas.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Pytest configuration and shared fixtures
├── test_enums.py            # Tests for all enum classes
├── test_models.py           # Tests for Pydantic models
├── test_validation.py       # Tests for validation and error handling
├── test_serialization.py    # Tests for JSON serialization/deserialization
└── README.md               # This file
```

## Test Coverage

The test suite provides **100% coverage** for all schema components:

- **Enums**: TaskPriority, TaskStatus, EntityType, AgentType, WorkerType
- **Models**: CostMetrics, TaskMessage, ResultMessage
- **Validation**: Error handling, edge cases, type checking
- **Serialization**: JSON round-trip testing, complex data structures

## Running Tests

### Quick Test Run

```bash
python3 -m pytest tests/ -v
```

### With Coverage Report

```bash
python3 -m pytest tests/ --cov=schemas --cov-report=term-missing
```

### Using the Test Runner Script

```bash
./run_tests.py
```

### Generate HTML Coverage Report

```bash
python3 -m pytest tests/ --cov=schemas --cov-report=html:htmlcov
```

## Test Categories

### 1. Enum Tests (`test_enums.py`)

- **Value validation**: Ensures all enum values are correct
- **Member validation**: Verifies all expected members exist
- **Comparison operations**: Tests enum equality and value comparison
- **String representation**: Tests `str()` and `repr()` methods
- **Integration**: Tests consistency between related enums

### 2. Model Tests (`test_models.py`)

- **Creation**: Tests model instantiation with various parameters
- **Validation**: Tests field validation and type checking
- **Integration**: Tests interaction between different models
- **Edge cases**: Tests with minimal and maximal data

### 3. Validation Tests (`test_validation.py`)

- **Error handling**: Tests validation errors with invalid inputs
- **Edge cases**: Tests with extreme values, unicode, large data
- **Optional fields**: Tests None values and optional field behavior
- **Custom validation**: Tests complex validation scenarios

### 4. Serialization Tests (`test_serialization.py`)

- **JSON serialization**: Tests model-to-JSON conversion
- **JSON deserialization**: Tests JSON-to-model conversion
- **Round-trip testing**: Ensures data integrity through serialization cycles
- **Complex data**: Tests with nested structures, unicode, large datasets

## Test Fixtures

The `conftest.py` file provides shared fixtures for testing:

- `sample_task_id`: Sample UUID for task testing
- `sample_correlation_id`: Sample UUID for correlation testing
- `sample_context`: Sample context dictionary for task testing
- `sample_cost_metrics`: Sample cost metrics for result testing

## Dependencies

The test suite requires:

- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking utilities
- `pydantic` - Schema validation (already in project)

## Configuration

Test configuration is in `pytest.ini`:

- Test discovery patterns
- Coverage settings
- Output formatting
- HTML report generation

## Best Practices

1. **Comprehensive Coverage**: Every schema component is tested
2. **Edge Cases**: Tests include boundary conditions and error scenarios
3. **Real-world Data**: Tests use realistic data structures and values
4. **Performance**: Tests include performance considerations for large data
5. **Maintainability**: Tests are well-documented and organized by functionality

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

- Fast execution (< 1 second)
- Deterministic results
- Clear error reporting
- Coverage metrics
- No external dependencies

## Schema Validation

The tests ensure that all schemas:

- ✅ Validate input data correctly
- ✅ Handle edge cases gracefully
- ✅ Serialize/deserialize properly
- ✅ Maintain data integrity
- ✅ Provide clear error messages
- ✅ Support all required use cases
