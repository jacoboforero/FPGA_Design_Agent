# Multi-Agent Hardware Design System - Test Suite

This directory contains comprehensive tests for the multi-agent hardware design system, organized by component.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Global pytest configuration and shared fixtures
├── schemas/                 # Schema validation tests
│   ├── __init__.py
│   ├── conftest.py          # Schema-specific fixtures
│   ├── test_enums.py        # Enum class tests
│   ├── test_models.py       # Pydantic model tests
│   ├── test_validation.py   # Validation and error handling tests
│   ├── test_serialization.py # JSON serialization tests
│   └── README.md           # Schema testing documentation
└── [other components]/      # Additional component tests (future)
```

## Running Tests

### Run All Tests

```bash
python3 -m pytest tests/ -v
```

### Run Schema Tests Only

```bash
python3 -m pytest tests/schemas/ -v
```

### Run with Coverage

```bash
python3 -m pytest tests/ --cov=schemas --cov-report=term-missing
```

### Run Specific Component Tests

```bash
# Schema tests
python3 -m pytest tests/schemas/ -v

# Future: Additional component tests
python3 -m pytest tests/[component]/ -v
```

## Test Organization Philosophy

### Component-Based Testing

Each major system component has its own test directory:

- **`schemas/`** - Data contract validation
- **`[other components]/`** - Additional component tests as needed

### Shared vs Component-Specific

- **Global fixtures** (`tests/conftest.py`) - System-wide test utilities
- **Component fixtures** (`tests/schemas/conftest.py`) - Schema-specific test data
- **Isolated testing** - Each component can be tested independently

### Scalability

This structure supports:

- **Parallel development** - Teams can work on different components
- **Selective testing** - Run only relevant tests during development
- **CI/CD optimization** - Test only changed components
- **Clear ownership** - Each component has dedicated test space

## Current Test Coverage

### ✅ Schema Tests (Complete)

- **67 tests** covering all data contracts
- **100% coverage** of schema validation
- **Comprehensive validation** of enums, models, serialization

### 🔄 Future Components (Planned)

- **Additional component tests** - As new components are developed

## Best Practices

1. **Component Isolation** - Each component's tests are independent
2. **Shared Utilities** - Common test helpers in global `conftest.py`
3. **Clear Naming** - Test files clearly indicate what they test
4. **Comprehensive Coverage** - Each component has thorough test coverage
5. **Fast Execution** - Tests run quickly for rapid development feedback

## Development Workflow

```bash
# During schema development
python3 -m pytest tests/schemas/ -v

# During component development
python3 -m pytest tests/[component]/ -v

# Before committing
python3 -m pytest tests/ -v --cov

# CI/CD pipeline
python3 -m pytest tests/ --cov --cov-report=xml
```

This structure ensures the test suite scales with your system while maintaining clear organization and fast execution.
