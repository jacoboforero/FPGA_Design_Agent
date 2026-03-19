#!/usr/bin/env python3
"""
Run the project's pytest suite and display a Rich summary table.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from rich import box
from rich.console import Console
from rich.table import Table

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TestSuiteMeta:
    """Metadata needed to describe each logical test suite."""

    path: Path
    display_name: str
    suite_type: str  # "Unit" or "Integration"
    description: str


TEST_SUITES: List[TestSuiteMeta] = [
    TestSuiteMeta(
        path=Path("tests/core/schemas/test_serialization.py"),
        display_name="test_serialization.py",
        suite_type="Unit",
        description="Validates JSON serialization/deserialization fidelity for all schema models.",
    ),
    TestSuiteMeta(
        path=Path("tests/core/schemas/test_models.py"),
        display_name="test_models.py",
        suite_type="Unit",
        description="Exercises the Pydantic task/result/analysis models across valid, edge, and integration scenarios.",
    ),
    TestSuiteMeta(
        path=Path("tests/core/schemas/test_enums.py"),
        display_name="test_enums.py",
        suite_type="Unit",
        description="Confirms enum definitions for priorities, statuses, entities, agents, and workers stay stable.",
    ),
    TestSuiteMeta(
        path=Path("tests/core/schemas/test_specifications.py"),
        display_name="test_specifications.py",
        suite_type="Unit",
        description="Ensures the hierarchical L1-L5 specification schemas and FrozenSpecification invariants behave consistently.",
    ),
    TestSuiteMeta(
        path=Path("tests/core/schemas/test_validation.py"),
        display_name="test_validation.py",
        suite_type="Unit",
        description="Stresses validation and error handling paths for every schema, including extreme edge cases.",
    ),
    TestSuiteMeta(
        path=Path("tests/infrastructure/test_docker_setup.py"),
        display_name="test_docker_setup.py",
        suite_type="Integration",
        description="Verifies docker-compose assets, RabbitMQ definitions, and management endpoints come up healthy.",
    ),
    TestSuiteMeta(
        path=Path("tests/infrastructure/test_message_flow.py"),
        display_name="test_message_flow.py",
        suite_type="Integration",
        description="Exercises RabbitMQ publish/consume flows for tasks/results with priority and persistence checks.",
    ),
    TestSuiteMeta(
        path=Path("tests/infrastructure/test_schema_integration.py"),
        display_name="test_schema_integration.py",
        suite_type="Integration",
        description="Checks schema enums align with RabbitMQ routing keys and serialization expectations.",
    ),
    TestSuiteMeta(
        path=Path("tests/infrastructure/test_queue_configuration.py"),
        display_name="test_queue_configuration.py",
        suite_type="Integration",
        description="Validates RabbitMQ queues, exchanges, bindings, and priority arguments exist per definitions.",
    ),
    TestSuiteMeta(
        path=Path("tests/infrastructure/test_dlq_functionality.py"),
        display_name="test_dlq_functionality.py",
        suite_type="Integration",
        description="Validates DLX/DLQ plumbing including message rejection flows, headers, and monitoring heuristics.",
    ),
]


class ResultCollector:
    """Pytest plugin that records per-file pass/fail counts."""

    def __init__(self, root: Path):
        self.root = root
        self.results: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"passed": 0, "failed": 0, "skipped": 0, "total": 0}
        )

    def _normalize(self, raw_path: str) -> str:
        path_obj = Path(raw_path)
        if not path_obj.is_absolute():
            path_obj = (self.root / path_obj).resolve()
        try:
            rel_path = path_obj.relative_to(self.root)
        except ValueError:
            rel_path = path_obj
        return rel_path.as_posix()

    def pytest_runtest_logreport(self, report):  # type: ignore[override]
        """Hook invoked for each test report."""
        is_skip = getattr(report, "skipped", False)
        if is_skip:
            key = self._normalize(report.location[0])
            bucket = self.results[key]
            bucket["skipped"] += 1
            return

        if report.when != "call":
            return

        key = self._normalize(report.location[0])
        bucket = self.results[key]
        bucket["total"] += 1

        if report.passed:
            bucket["passed"] += 1
        elif report.failed:
            bucket["failed"] += 1
        elif is_skip:
            bucket["skipped"] += 1


def run_pytest() -> Tuple[int, Dict[str, Dict[str, int]]]:
    """Execute pytest once and return (exit_code, per-file results)."""
    os.chdir(PROJECT_ROOT)
    collector = ResultCollector(PROJECT_ROOT)
    exit_code = pytest.main(["tests", "-q"], plugins=[collector])
    return exit_code, collector.results


def build_table(results: Dict[str, Dict[str, int]]) -> Table:
    """Create a Rich table visualizing the collected results."""
    table = Table(
        title="Test Results Summary",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
    )
    table.add_column("Test Suite", style="bold", justify="left")
    table.add_column("Type", justify="center")
    table.add_column("Description", justify="left", overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Count", justify="center")

    for suite in TEST_SUITES:
        key = suite.path.as_posix()
        file_result = results.get(key) or results.get(f"./{key}") or {"passed": 0, "failed": 0, "skipped": 0, "total": 0}
        executed = file_result["total"]
        passed = file_result["passed"]
        failed = file_result["failed"]
        skipped = file_result["skipped"]

        status_text = "[green]Pass[/green]" if failed == 0 else "[red]Fail[/red]"

        if executed > 0:
            count_text = f"{passed}/{executed} passed"
        else:
            count_text = "0/0 passed"

        if skipped > 0:
            count_text += f" (+{skipped} skipped)"

        table.add_row(
            suite.display_name,
            suite.suite_type,
            suite.description,
            status_text,
            count_text,
        )

    return table


def main() -> None:
    exit_code, results = run_pytest()
    console = Console()
    console.print(build_table(results))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
