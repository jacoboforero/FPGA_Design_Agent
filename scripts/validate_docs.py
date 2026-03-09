#!/usr/bin/env python3
"""
Validate documentation quality guardrails.

This script focuses on two checks:
1) Local markdown link integrity for docs and top-level README.
2) Optional command-smoke checks for key documented CLI examples.

Usage:
  python3 scripts/validate_docs.py
  python3 scripts/validate_docs.py --run-commands
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = REPO_ROOT / "docs"

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")


def _iter_markdown_files() -> list[Path]:
    files = sorted(DOC_ROOT.rglob("*.md"))
    files.append(REPO_ROOT / "README.md")
    return [path for path in files if path.exists()]


def _normalize_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target


def _is_external_target(target: str) -> bool:
    low = target.lower()
    return low.startswith(EXTERNAL_PREFIXES)


def _check_markdown_links() -> list[str]:
    errors: list[str] = []
    files = _iter_markdown_files()
    for md_path in files:
        text = md_path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_RE.finditer(text):
            raw_target = _normalize_target(match.group(1))
            if not raw_target:
                continue
            if _is_external_target(raw_target):
                continue

            path_part = raw_target.split("#", 1)[0].strip()
            if not path_part:
                # same-file anchor link; do not validate anchor text here
                continue

            if path_part.startswith("/"):
                target_path = Path(path_part)
            else:
                target_path = (md_path.parent / path_part).resolve()
            if not target_path.exists():
                errors.append(f"{md_path.relative_to(REPO_ROOT)} -> missing link target: {raw_target}")
    return errors


def _command_checks() -> list[tuple[str, str]]:
    tmp_report = Path(tempfile.gettempdir()) / "docs_validate_campaign_report.json"
    return [
        (
            "CLI help",
            "PYTHONPATH=. python3 apps/cli/cli.py --help",
        ),
        (
            "Benchmark help",
            "PYTHONPATH=. python3 apps/cli/cli.py benchmark --help",
        ),
        (
            "Benchmark list-problems smoke",
            "PYTHONPATH=. python3 apps/cli/cli.py benchmark list-problems --preset benchmark --max-problems 1",
        ),
        (
            "Benchmark run dry-run smoke",
            "PYTHONPATH=. python3 apps/cli/cli.py benchmark run --preset benchmark --campaign docs_validate --run-id dryrun --max-problems 1 --dry-run",
        ),
        (
            "Campaign runner help",
            "python3 scripts/run_benchmark_campaign.py --help",
        ),
        (
            "Campaign runner dry-run smoke",
            (
                "python3 scripts/run_benchmark_campaign.py "
                "--campaign-file benchmarks/verilog_eval/campaign.example.yaml "
                "--dry-run --report-out "
                f"{tmp_report}"
            ),
        ),
    ]


def _run_shell(command: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    merged = output
    if err:
        merged = (merged + "\n" + err).strip() if merged else err
    return int(proc.returncode), merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate docs links and optional command examples.")
    parser.add_argument(
        "--run-commands",
        action="store_true",
        help="Run command-smoke checks for documented CLI examples.",
    )
    args = parser.parse_args()

    link_errors = _check_markdown_links()
    if link_errors:
        print("[FAIL] Broken markdown links detected:")
        for item in link_errors:
            print(f"- {item}")
        return 1
    print("[PASS] Markdown link validation")

    if not args.run_commands:
        print("[INFO] Command-smoke checks skipped (use --run-commands to enable)")
        return 0

    failures: list[str] = []
    checks = _command_checks()
    for label, command in checks:
        code, output = _run_shell(command)
        if code == 0:
            print(f"[PASS] {label}")
            continue
        print(f"[FAIL] {label}")
        snippet = output.splitlines()[:8]
        for line in snippet:
            print(f"  {line}")
        failures.append(label)

    if failures:
        print("\nCommand-smoke failures:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("[PASS] Command-smoke validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
