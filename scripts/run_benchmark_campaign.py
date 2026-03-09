#!/usr/bin/env python3
"""
Run a benchmark campaign composed of multiple benchmark run entries.

Example campaign file:
---
campaign: model_sweep_march
output_root: artifacts/benchmarks/verilog_eval
runs:
  - label: gpt41_canonical
    config: config/runtime.yaml
    preset: benchmark
    sampled: false
    max_problems: 20
  - label: gpt41_sampled
    config: config/runtime.yaml
    preset: benchmark
    sampled: true
    max_problems: 20
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = "config/runtime.yaml"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str | None, *, default: str) -> str:
    raw = str(text or "").strip()
    out = "".join(ch if (ch.isalnum() or ch in "._-") else "-" for ch in raw).strip("-._")
    return out or default


def _load_campaign(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Campaign file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"Campaign file must contain a YAML object: {path}")
    runs = payload.get("runs")
    if not isinstance(runs, list) or not runs:
        raise RuntimeError("Campaign file must define a non-empty 'runs' list.")
    return payload


def _bool_flag(args: list[str], name: str, value: bool) -> None:
    if value:
        args.append(name)


def _build_run_command(
    *,
    python_bin: str,
    campaign_name: str,
    campaign_output_root: str | None,
    run_item: dict[str, Any],
) -> tuple[list[str], Path]:
    label = _slug(str(run_item.get("label", "")), default="run")
    config = str(run_item.get("config") or DEFAULT_CONFIG)
    preset = str(run_item.get("preset") or "benchmark")
    run_id = _slug(str(run_item.get("run_id") or label), default=label)
    output_root = str(run_item.get("output_root") or campaign_output_root or "").strip()
    run_dir = str(run_item.get("run_dir") or "").strip()

    cmd: list[str] = [
        python_bin,
        "apps/cli/cli.py",
        "benchmark",
        "run",
        "--config",
        config,
        "--preset",
        preset,
        "--campaign",
        campaign_name,
        "--run-id",
        run_id,
    ]

    if output_root:
        cmd.extend(["--output-root", output_root])
    if run_dir:
        cmd.extend(["--run-dir", run_dir])

    _bool_flag(cmd, "--sampled", bool(run_item.get("sampled", False)))
    _bool_flag(cmd, "--legacy-lightweight", bool(run_item.get("legacy_lightweight", False)))
    _bool_flag(cmd, "--resume", bool(run_item.get("resume", False)))
    _bool_flag(cmd, "--overwrite", bool(run_item.get("overwrite", False)))
    _bool_flag(cmd, "--purge-queues", bool(run_item.get("purge_queues", False)))

    if "pipeline_timeout" in run_item:
        cmd.extend(["--pipeline-timeout", str(float(run_item["pipeline_timeout"]))])
    if "max_problems" in run_item:
        cmd.extend(["--max-problems", str(int(run_item["max_problems"]))])

    only_problem = run_item.get("only_problem") or []
    if isinstance(only_problem, str):
        only_problem = [only_problem]
    for item in only_problem:
        text = str(item).strip()
        if text:
            cmd.extend(["--only-problem", text])

    extra_args = run_item.get("extra_args") or []
    if isinstance(extra_args, list):
        cmd.extend(str(item) for item in extra_args)

    if run_dir:
        run_root = Path(run_dir).resolve()
    else:
        root = Path(output_root).resolve() if output_root else (REPO_ROOT / "artifacts" / "benchmarks" / "verilog_eval")
        run_root = root / campaign_name / run_id
    return cmd, run_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-entry benchmark campaigns from YAML.")
    parser.add_argument("--campaign-file", required=True, help="Path to campaign YAML file.")
    parser.add_argument("--python-bin", default=sys.executable, help="Python interpreter to use.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue executing remaining entries when a run fails.",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Optional output path for campaign report JSON (default: campaign root/campaign_report.json).",
    )
    args = parser.parse_args()

    campaign_file = Path(args.campaign_file).resolve()
    campaign = _load_campaign(campaign_file)
    campaign_name = _slug(str(campaign.get("campaign") or campaign_file.stem), default="campaign")
    campaign_output_root = str(campaign.get("output_root") or "").strip() or None
    runs = campaign.get("runs", [])

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = f".:{existing_pythonpath}" if existing_pythonpath else "."

    summary: dict[str, Any] = {
        "campaign": campaign_name,
        "campaign_file": str(campaign_file),
        "started_at": _utc_now_iso(),
        "finished_at": "",
        "dry_run": bool(args.dry_run),
        "runs": [],
    }

    failures = 0
    for index, raw in enumerate(runs, start=1):
        if not isinstance(raw, dict):
            raise RuntimeError(f"Invalid run entry at index {index}: expected mapping.")
        cmd, run_root = _build_run_command(
            python_bin=str(args.python_bin),
            campaign_name=campaign_name,
            campaign_output_root=campaign_output_root,
            run_item=raw,
        )
        label = _slug(str(raw.get("label") or f"run{index:02d}"), default=f"run{index:02d}")
        print(f"[{index}/{len(runs)}] {label}")
        print("  " + " ".join(cmd))
        entry = {
            "label": label,
            "command": cmd,
            "run_root": str(run_root),
            "started_at": _utc_now_iso(),
            "finished_at": "",
            "status": "dry_run" if args.dry_run else "pending",
            "returncode": None,
        }
        if not args.dry_run:
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, check=False)
            entry["returncode"] = int(proc.returncode)
            entry["status"] = "success" if proc.returncode == 0 else "failed"
            if proc.returncode != 0:
                failures += 1
                if not args.continue_on_error:
                    entry["finished_at"] = _utc_now_iso()
                    summary["runs"].append(entry)
                    break
        entry["finished_at"] = _utc_now_iso()
        summary["runs"].append(entry)

    summary["finished_at"] = _utc_now_iso()
    summary["failure_count"] = failures
    summary["run_count"] = len(summary["runs"])

    if args.report_out:
        report_path = Path(args.report_out).resolve()
    else:
        if campaign_output_root:
            report_path = Path(campaign_output_root).resolve() / campaign_name / "campaign_report.json"
        else:
            report_path = REPO_ROOT / "artifacts" / "benchmarks" / "verilog_eval" / campaign_name / "campaign_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Campaign report: {report_path}")

    if failures > 0 and not args.dry_run:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
