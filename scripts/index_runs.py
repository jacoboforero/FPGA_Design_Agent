#!/usr/bin/env python3
"""Build a non-destructive index over run artifacts and create organized views.

This script does not move or delete historical raw outputs. It writes:
- artifacts/index/*.csv + summary.json
- artifacts/organized/* symlink-based campaign views (optional)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OBS_FILE_SUFFIXES = {
    "_events.jsonl": "events",
    "_summary.json": "summary",
    "_execution_metrics.json": "execution_metrics",
}


def utc_iso(epoch_seconds: float | None) -> str:
    if not epoch_seconds:
        return ""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def scan_tree_stats(root: Path) -> tuple[int, int, float]:
    if not root.exists():
        return 0, 0, 0.0
    file_count = 0
    byte_count = 0
    newest = 0.0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        file_count += 1
        byte_count += stat.st_size
        newest = max(newest, stat.st_mtime)
    return file_count, byte_count, newest


def detect_family(run_name: str) -> str:
    if run_name.startswith("cli_full_"):
        return "cli_full"
    if run_name.startswith("matrix_"):
        return "matrix"
    if run_name.startswith("benchmark_"):
        return "benchmark"
    if run_name.startswith("session"):
        return "session"
    return "other"


def detect_campaign(run_name: str, family: str) -> str:
    low = run_name.lower()
    if family == "matrix":
        return "matrix_testspec_sweep"
    if low.startswith("benchmark_canonical_"):
        return "canonical_misc"
    if low.startswith("benchmark_sampled_"):
        return "canonical_misc"
    if "counter3-gpt41" in low:
        return "counter3_consistency_gpt41"
    if "counter3-mini" in low:
        return "counter3_consistency_mini"
    if "counter3-lowrisk" in low:
        return "counter3_consistency_lowrisk"
    if "consistency" in low:
        return "counter3_consistency_misc"
    if "wavefix_failed41" in low:
        return "wavefix_failed41_subset"
    if "wavefix" in low:
        return "wavefix_smoke"
    if "canonical_full_156" in low:
        return "canonical_full_156"
    if "canonical_part1_143" in low:
        return "canonical_part1_143"
    if "canonical" in low:
        return "canonical_misc"
    if re.search(r"\d{8}", run_name):
        return "dated_ad_hoc"
    return "misc"


def safe_read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def build_observability_index(repo_root: Path, artifacts_root: Path) -> tuple[list[dict[str, Any]], Counter]:
    observability_root = artifacts_root / "observability"
    runs_root = observability_root / "runs"
    by_run: dict[str, dict[str, Any]] = defaultdict(dict)

    if observability_root.exists():
        for path in observability_root.iterdir():
            if not path.is_file():
                continue
            for suffix, label in OBS_FILE_SUFFIXES.items():
                if not path.name.endswith(suffix):
                    continue
                run_name = path.name[: -len(suffix)]
                rec = by_run[run_name]
                rec["run_name"] = run_name
                rec[f"{label}_path"] = rel(path, repo_root)
                rec[f"has_{label}"] = "1"
                rec["root_file_count"] = int(rec.get("root_file_count", 0)) + 1
                rec["root_bytes"] = int(rec.get("root_bytes", 0)) + path.stat().st_size
                rec["last_modified_epoch"] = max(float(rec.get("last_modified_epoch", 0.0)), path.stat().st_mtime)

    if runs_root.exists():
        for run_name_dir in runs_root.iterdir():
            if not run_name_dir.is_dir():
                continue
            run_name = run_name_dir.name
            rec = by_run[run_name]
            rec["run_name"] = run_name
            rec["runs_dir_path"] = rel(run_name_dir, repo_root)
            run_id_dirs = [p for p in run_name_dir.iterdir() if p.is_dir()]
            rec["run_id_count"] = len(run_id_dirs)
            run_files = 0
            run_bytes = 0
            run_latest = 0.0
            for run_id_dir in run_id_dirs:
                files, bytes_, newest = scan_tree_stats(run_id_dir)
                run_files += files
                run_bytes += bytes_
                run_latest = max(run_latest, newest)
            rec["runs_tree_file_count"] = run_files
            rec["runs_tree_bytes"] = run_bytes
            rec["last_modified_epoch"] = max(float(rec.get("last_modified_epoch", 0.0)), run_latest)

    rows: list[dict[str, Any]] = []
    campaign_counts: Counter = Counter()
    for run_name in sorted(by_run):
        rec = by_run[run_name]
        family = detect_family(run_name)
        campaign = detect_campaign(run_name, family)
        campaign_counts[campaign] += 1
        rows.append(
            {
                "run_name": run_name,
                "family": family,
                "campaign": campaign,
                "has_events": rec.get("has_events", "0"),
                "has_summary": rec.get("has_summary", "0"),
                "has_execution_metrics": rec.get("has_execution_metrics", "0"),
                "events_path": rec.get("events_path", ""),
                "summary_path": rec.get("summary_path", ""),
                "execution_metrics_path": rec.get("execution_metrics_path", ""),
                "runs_dir_path": rec.get("runs_dir_path", ""),
                "run_id_count": rec.get("run_id_count", 0),
                "root_file_count": rec.get("root_file_count", 0),
                "root_bytes": rec.get("root_bytes", 0),
                "runs_tree_file_count": rec.get("runs_tree_file_count", 0),
                "runs_tree_bytes": rec.get("runs_tree_bytes", 0),
                "last_modified_utc": utc_iso(float(rec.get("last_modified_epoch", 0.0))),
            }
        )
    return rows, campaign_counts


def build_benchmark_index(repo_root: Path, artifacts_root: Path) -> tuple[list[dict[str, Any]], Counter]:
    benchmark_root = artifacts_root / "benchmarks" / "verilog_eval"
    if not benchmark_root.exists():
        return [], Counter()

    rows: list[dict[str, Any]] = []
    campaign_counts: Counter = Counter()
    seen_dirs: set[str] = set()
    for aggregate_path in sorted(benchmark_root.rglob("aggregate.json")):
        mode_dir = aggregate_path.parent
        rel_mode = rel(mode_dir, repo_root)
        if rel_mode in seen_dirs:
            continue
        seen_dirs.add(rel_mode)

        summary_csv_path = mode_dir / "summary.csv"
        summary_txt_path = mode_dir / "summary.txt"
        if not summary_csv_path.exists() and not summary_txt_path.exists():
            # Ignore unrelated aggregate files that do not look like benchmark outputs.
            continue

        aggregate = safe_read_json(aggregate_path)
        aggregate_block = aggregate.get("aggregate", {}) if isinstance(aggregate.get("aggregate"), dict) else {}
        official_metrics = aggregate_block.get("official_metrics", {}) if isinstance(aggregate_block.get("official_metrics"), dict) else {}
        per_problem = aggregate.get("per_problem", []) if isinstance(aggregate.get("per_problem"), list) else []

        pass_count = 0
        sample_count = 0
        for row in per_problem:
            if not isinstance(row, dict):
                continue
            try:
                pass_count += int(float(row.get("npass", 0) or 0))
            except Exception:
                pass
            try:
                sample_count += int(float(row.get("nsamples", 0) or 0))
            except Exception:
                pass

        row_count = aggregate_block.get("row_count", len(per_problem))
        pass_rate = official_metrics.get("pass_rate", "")
        if pass_rate in ("", None) and sample_count > 0:
            pass_rate = pass_count / sample_count

        rel_parts = mode_dir.relative_to(benchmark_root).parts
        mode = rel_parts[-1] if rel_parts and rel_parts[-1] in {"canonical", "sampled"} else ""
        if len(rel_parts) >= 3 and mode:
            campaign_dir = rel_parts[-3]
            run_id = rel_parts[-2]
            run_root = benchmark_root / campaign_dir / run_id
        else:
            campaign_dir = rel_parts[0] if rel_parts else "benchmark"
            run_id = ""
            run_root = mode_dir

        manifest_path = run_root / "run_manifest.json"
        manifest = safe_read_json(manifest_path) if manifest_path.exists() else {}
        runtime = manifest.get("runtime", {}) if isinstance(manifest.get("runtime"), dict) else {}
        llm = runtime.get("llm", {}) if isinstance(runtime.get("llm"), dict) else {}

        files, bytes_, newest = scan_tree_stats(mode_dir)
        campaign = detect_campaign(campaign_dir, "benchmark")
        campaign_counts[campaign] += 1
        rows.append(
            {
                "campaign_dir": campaign_dir,
                "run_id": run_id,
                "mode": mode,
                "campaign": campaign,
                "path": rel(mode_dir, repo_root),
                "run_root": rel(run_root, repo_root),
                "has_manifest": "1" if manifest_path.exists() else "0",
                "manifest_path": rel(manifest_path, repo_root) if manifest_path.exists() else "",
                "model": llm.get("default_model", ""),
                "provider": llm.get("provider", ""),
                "preset": manifest.get("preset", ""),
                "status": manifest.get("status", ""),
                "has_aggregate_json": "1",
                "has_summary_csv": "1" if summary_csv_path.exists() else "0",
                "has_summary_txt": "1" if summary_txt_path.exists() else "0",
                "row_count": row_count,
                "pass_count": pass_count,
                "sample_count": sample_count,
                "pass_rate": pass_rate,
                "total_tokens": official_metrics.get("total_tokens", ""),
                "total_cost": official_metrics.get("total_cost", ""),
                "file_count": files,
                "byte_count": bytes_,
                "last_modified_utc": utc_iso(newest),
            }
        )
    rows.sort(key=lambda item: item.get("path", ""))
    return rows, campaign_counts


def build_matrix_index(repo_root: Path, artifacts_root: Path) -> list[dict[str, Any]]:
    matrix_root = artifacts_root / "matrix_runs"
    classified = matrix_root / "latest_summary_classified.csv"
    regular = matrix_root / "latest_summary.csv"
    source = classified if classified.exists() else regular
    if not source.exists():
        return []

    rows: list[dict[str, Any]] = []
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            run_name = row.get("run_name", "")
            rows.append(
                {
                    "run_name": run_name,
                    "campaign": detect_campaign(run_name, "matrix"),
                    "spec": row.get("spec", ""),
                    "run_idx": row.get("run_idx", ""),
                    "status": row.get("status", ""),
                    "true_status": row.get("true_status", ""),
                    "reason": row.get("reason", ""),
                    "true_reason": row.get("true_reason", ""),
                    "duration_s": row.get("duration_s", ""),
                    "log_path": row.get("log_path", ""),
                    "source_csv": rel(source, repo_root),
                }
            )
    return rows


def build_legacy_dir_index(repo_root: Path, artifacts_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    organized_root = (artifacts_root / "organized").resolve()
    for path in artifacts_root.rglob("*"):
        if not path.is_dir():
            continue
        if path.is_symlink():
            continue
        try:
            if path.resolve().is_relative_to(organized_root):
                continue
        except Exception:
            pass
        reason = ""
        if re.search(r" \d+$", path.name):
            reason = "suffix_space_number"
        elif "backup" in path.name.lower():
            reason = "backup_named_dir"
        if not reason:
            continue
        key = rel(path, repo_root)
        if key in seen:
            continue
        seen.add(key)
        files, bytes_, newest = scan_tree_stats(path)
        rows.append(
            {
                "path": key,
                "reason": reason,
                "file_count": files,
                "byte_count": bytes_,
                "last_modified_utc": utc_iso(newest),
            }
        )
    return sorted(rows, key=lambda x: x["path"])


def ensure_fresh_dir(path: Path) -> None:
    if path.exists() or path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def force_symlink(link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or link_path.exists():
        if link_path.is_dir() and not link_path.is_symlink():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()
    rel_target = os.path.relpath(target_path, start=link_path.parent)
    link_path.symlink_to(rel_target)


def build_organized_view(
    repo_root: Path,
    artifacts_root: Path,
    observability_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    matrix_rows: list[dict[str, Any]],
) -> None:
    organized_root = artifacts_root / "organized"
    ensure_fresh_dir(organized_root)

    campaigns_root = organized_root / "campaigns"
    for row in observability_rows:
        campaign = row.get("campaign", "misc")
        run_name = row.get("run_name", "")
        if not run_name:
            continue
        campaign_root = campaigns_root / campaign
        run_dir_rel = row.get("runs_dir_path", "")
        if run_dir_rel:
            source_dir = repo_root / run_dir_rel
            if source_dir.exists():
                force_symlink(campaign_root / "runs" / run_name, source_dir)
        for kind in ("events", "summary", "execution_metrics"):
            path_rel = row.get(f"{kind}_path", "")
            if not path_rel:
                continue
            source_file = repo_root / path_rel
            if source_file.exists():
                force_symlink(campaign_root / "observability_files" / source_file.name, source_file)

    benchmarks_root = organized_root / "benchmarks"
    for row in benchmark_rows:
        source = repo_root / row["path"]
        if source.exists():
            campaign_dir = str(row.get("campaign_dir", "benchmark"))
            run_id = str(row.get("run_id", ""))
            mode = str(row.get("mode", ""))
            if run_id and mode:
                link_path = benchmarks_root / campaign_dir / run_id / mode
            elif mode:
                link_path = benchmarks_root / campaign_dir / mode
            else:
                link_path = benchmarks_root / campaign_dir
            force_symlink(link_path, source)

    if matrix_rows:
        matrix_root = artifacts_root / "matrix_runs"
        if matrix_root.exists():
            force_symlink(organized_root / "matrix" / "matrix_runs", matrix_root)


def build_campaign_summary(
    observability_counts: Counter,
    benchmark_counts: Counter,
    matrix_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts = Counter(observability_counts)
    counts.update(benchmark_counts)
    for row in matrix_rows:
        counts[row.get("campaign", "matrix_testspec_sweep")] += 1
    rows = [{"campaign": k, "artifact_groups": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root (default: cwd)")
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=None,
        help="Artifacts root (default: <repo-root>/artifacts)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Index output directory (default: <artifacts-root>/index)",
    )
    parser.add_argument(
        "--build-links",
        action="store_true",
        help="Create artifacts/organized symlink views grouped by campaign",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    artifacts_root = (args.artifacts_root or (repo_root / "artifacts")).resolve()
    out_dir = (args.out_dir or (artifacts_root / "index")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    observability_rows, observability_counts = build_observability_index(repo_root, artifacts_root)
    benchmark_rows, benchmark_counts = build_benchmark_index(repo_root, artifacts_root)
    matrix_rows = build_matrix_index(repo_root, artifacts_root)
    legacy_rows = build_legacy_dir_index(repo_root, artifacts_root)
    campaign_rows = build_campaign_summary(observability_counts, benchmark_counts, matrix_rows)

    write_csv(
        out_dir / "observability_runs.csv",
        observability_rows,
        [
            "run_name",
            "family",
            "campaign",
            "has_events",
            "has_summary",
            "has_execution_metrics",
            "events_path",
            "summary_path",
            "execution_metrics_path",
            "runs_dir_path",
            "run_id_count",
            "root_file_count",
            "root_bytes",
            "runs_tree_file_count",
            "runs_tree_bytes",
            "last_modified_utc",
        ],
    )
    write_csv(
        out_dir / "benchmark_campaigns.csv",
        benchmark_rows,
        [
            "campaign_dir",
            "run_id",
            "mode",
            "campaign",
            "path",
            "run_root",
            "has_manifest",
            "manifest_path",
            "model",
            "provider",
            "preset",
            "status",
            "has_aggregate_json",
            "has_summary_csv",
            "has_summary_txt",
            "row_count",
            "pass_count",
            "sample_count",
            "pass_rate",
            "total_tokens",
            "total_cost",
            "file_count",
            "byte_count",
            "last_modified_utc",
        ],
    )
    write_csv(
        out_dir / "matrix_runs.csv",
        matrix_rows,
        [
            "run_name",
            "campaign",
            "spec",
            "run_idx",
            "status",
            "true_status",
            "reason",
            "true_reason",
            "duration_s",
            "log_path",
            "source_csv",
        ],
    )
    write_csv(
        out_dir / "legacy_dirs.csv",
        legacy_rows,
        ["path", "reason", "file_count", "byte_count", "last_modified_utc"],
    )
    write_csv(out_dir / "campaign_summary.csv", campaign_rows, ["campaign", "artifact_groups"])

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "repo_root": rel(repo_root, repo_root),
        "artifacts_root": rel(artifacts_root, repo_root),
        "counts": {
            "observability_runs": len(observability_rows),
            "benchmark_campaigns": len(benchmark_rows),
            "matrix_rows": len(matrix_rows),
            "legacy_dirs": len(legacy_rows),
            "campaigns": len(campaign_rows),
        },
        "outputs": {
            "observability_runs_csv": rel(out_dir / "observability_runs.csv", repo_root),
            "benchmark_campaigns_csv": rel(out_dir / "benchmark_campaigns.csv", repo_root),
            "matrix_runs_csv": rel(out_dir / "matrix_runs.csv", repo_root),
            "legacy_dirs_csv": rel(out_dir / "legacy_dirs.csv", repo_root),
            "campaign_summary_csv": rel(out_dir / "campaign_summary.csv", repo_root),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    if args.build_links:
        build_organized_view(repo_root, artifacts_root, observability_rows, benchmark_rows, matrix_rows)

    print("Artifact indexing complete.")
    print(f"- observability runs: {len(observability_rows)}")
    print(f"- benchmark campaigns: {len(benchmark_rows)}")
    print(f"- matrix rows: {len(matrix_rows)}")
    print(f"- legacy dirs: {len(legacy_rows)}")
    print(f"- index output: {rel(out_dir, repo_root)}")
    if args.build_links:
        print(f"- organized links: {rel(artifacts_root / 'organized', repo_root)}")


if __name__ == "__main__":
    main()
