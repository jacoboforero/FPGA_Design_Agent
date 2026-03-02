"""
VerilogEval runner with official analyzer parity.

This command executes benchmark cases and delegates scoring to the official
VerilogEval scripts/artifacts (``summary.txt``, ``summary.csv``).
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import pika

from agents.implementation.worker import ImplementationWorker
from apps.cli import spec_flow
from apps.cli.cli import connection_params_from_config, start_workers, stop_workers
from core.observability.agentops_tracker import get_tracker
from core.runtime.broker import create_run_routing, declare_task_topology
from core.runtime.config import DEFAULT_CONFIG_PATH, get_runtime_config, set_runtime_config
from core.schemas.contracts import AgentType, EntityType, TaskMessage, TaskStatus
from orchestrator import planner
from orchestrator.context_builder import DemoContextBuilder
from orchestrator.orchestrator_service import DemoOrchestrator

PROBLEM_RE = re.compile(r"^(Prob\d+)", re.IGNORECASE)
SUMMARY_KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([-+]?[0-9]*\.?[0-9]+)\s*$")
TOP_MODULE_INSTANCE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_$]*)\s+top_module\d*\s*\(", re.MULTILINE)
MODULE_NAMED_RE = re.compile(r"\bmodule named\s+([A-Za-z_][A-Za-z0-9_$]*)", re.IGNORECASE)
MODULE_DECL_RE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b")
MODULE_HEADER_RE = re.compile(r"\bmodule\s+[A-Za-z_][A-Za-z0-9_$]*\s*\((.*?)\)\s*;", re.DOTALL)
MODULE_PORT_RE = re.compile(
    r"\b(input|output|inout)\b\s*(?:reg|wire|logic)?\s*(\[[^]]+\])?\s*([A-Za-z_][A-Za-z0-9_$]*)",
    re.IGNORECASE,
)
MODULE_BLOCK_TEMPLATE = r"\bmodule\s+{name}\b.*?endmodule\b"
BODY_PORT_DECL_RE = re.compile(
    r"\b(input|output|inout)\b\s*(?:reg|wire|logic|signed|unsigned|\s)*(\[[^]]+\])?\s*([^;]+);",
    re.IGNORECASE,
)
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

_BENCHMARK_QUEUE_PURGE_LIST = (
    "agent_tasks",
    "process_tasks",
    "simulation_tasks",
    "agent_planner_tasks",
    "agent_impl_tasks",
    "agent_tb_tasks",
    "agent_reflect_tasks",
    "agent_debug_tasks",
    "agent_spec_helper_tasks",
    "process_lint_tasks",
    "process_tb_lint_tasks",
    "process_acceptance_tasks",
    "process_distill_tasks",
    "results",
)


@dataclass(frozen=True)
class PromptCase:
    problem_id: str
    prompt_path: Path
    test_sv: Path
    ref_sv: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VerilogEval-compatible benchmark scoring.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to runtime YAML config.")
    parser.add_argument("--preset", default="benchmark", help="Preset to use (default: benchmark).")
    parser.add_argument(
        "--sampled",
        action="store_true",
        help="Also run optional literature-compatible sampled setting (n=20, temp=0.8, top_p=0.95).",
    )
    parser.add_argument(
        "--legacy-lightweight",
        action="store_true",
        help=(
            "Use previous lightweight benchmark generation path (direct implementation call) "
            "instead of orchestrated pipeline execution."
        ),
    )
    parser.add_argument(
        "--pipeline-timeout",
        type=float,
        default=180.0,
        help="Per-sample orchestrated pipeline timeout in seconds (default: 180).",
    )
    parser.add_argument(
        "--build-dir",
        default=None,
        help="Analyze-only mode: existing build directory containing summary.csv/summary.txt.",
    )
    parser.add_argument(
        "--max-problems",
        type=int,
        default=0,
        help="Optional cap on number of prompt problems to run (0 = all).",
    )
    parser.add_argument(
        "--only-problem",
        action="append",
        default=[],
        help="Run only specific problem IDs (repeatable), e.g. --only-problem Prob079",
    )
    return parser


def _script_cmd(script: Path, args: list[str]) -> list[str]:
    if script.exists() and script.is_file():
        # Some upstream scripts use `#!/usr/bin/env python`; prefer python3 when
        # python is unavailable in PATH (common on modern macOS/Linux setups).
        try:
            shebang = script.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip()
        except Exception:  # noqa: BLE001
            shebang = ""
        if shebang.startswith("#!") and "python" in shebang and "python3" not in shebang:
            if shutil.which("python") is None and shutil.which("python3") is not None:
                return ["python3", str(script), *args]
    if script.exists() and script.is_file() and (script.stat().st_mode & 0o111):
        return [str(script), *args]
    return ["python3", str(script), *args]


def _run_cmd(cmd: list[str], *, cwd: Path, timeout_s: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s)


def _merge_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    chunks: list[str] = []
    if stdout:
        chunks.append(stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout)
    if stderr:
        chunks.append(stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr)
    return "\n".join(part.strip() for part in chunks if part and part.strip()).strip()


def _resolve_tool(configured: str | None, default_name: str) -> str | None:
    if configured:
        text = str(configured).strip()
        if not text:
            return None
        if "/" in text:
            path = Path(text)
            return str(path) if path.exists() else None
        return shutil.which(text)
    return shutil.which(default_name)


def _has_langchain_schema() -> bool:
    try:
        return importlib.util.find_spec("langchain.schema") is not None
    except ModuleNotFoundError:
        return False


def _ensure_framework(root: Path) -> Path:
    if not root.exists() or not root.is_dir():
        raise RuntimeError(
            f"VerilogEval framework missing at '{root}'. Initialize submodule:\n"
            "  git submodule update --init --recursive"
        )
    required = [
        root / "scripts" / "sv-iv-analyze",
        root / "Makefile.in",
        root / "dataset_spec-to-rtl",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise RuntimeError(
            f"VerilogEval framework appears incomplete. Missing: {joined}\n"
            "Re-run:\n"
            "  git submodule update --init --recursive"
        )
    return root / "dataset_spec-to-rtl"


def _resolve_dataset_pair(dataset_dir: Path, problem_id: str) -> tuple[Path, Path]:
    pid = problem_id
    pid_lower = problem_id.lower()
    test_candidates: list[Path] = [
        dataset_dir / f"{pid}_test.sv",
        dataset_dir / f"{pid_lower}_test.sv",
        dataset_dir / pid / f"{pid}_test.sv",
        dataset_dir / pid / "test.sv",
        dataset_dir / pid_lower / f"{pid_lower}_test.sv",
    ]
    test_candidates.extend(sorted(dataset_dir.glob(f"{pid}*_test.sv")))
    test_candidates.extend(sorted(dataset_dir.glob(f"{pid_lower}*_test.sv")))

    ref_candidates: list[Path] = [
        dataset_dir / f"{pid}_ref.sv",
        dataset_dir / f"{pid_lower}_ref.sv",
        dataset_dir / pid / f"{pid}_ref.sv",
        dataset_dir / pid / "ref.sv",
        dataset_dir / pid_lower / f"{pid_lower}_ref.sv",
    ]
    ref_candidates.extend(sorted(dataset_dir.glob(f"{pid}*_ref.sv")))
    ref_candidates.extend(sorted(dataset_dir.glob(f"{pid_lower}*_ref.sv")))

    seen: set[str] = set()
    test_sv: Path | None = None
    for path in test_candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            test_sv = path
            break

    seen.clear()
    ref_sv: Path | None = None
    for path in ref_candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            ref_sv = path
            break

    if not test_sv or not ref_sv:
        raise RuntimeError(
            f"Could not resolve test/ref assets for {problem_id} under {dataset_dir}. "
            "Expected *_test.sv and *_ref.sv files from the official dataset."
        )
    return test_sv, ref_sv


def _load_oracle_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise RuntimeError(f"Oracle manifest not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Oracle manifest must be a JSON object: {path}")
    out: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        test_sv = str(value.get("test_sv", "")).strip()
        ref_sv = str(value.get("ref_sv", "")).strip()
        if test_sv and ref_sv:
            out[key] = {"test_sv": test_sv, "ref_sv": ref_sv}
    return out


def _prompt_problem_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    name = path.name
    lower = name.lower()
    if lower in {"problems.txt", "samples.txt", "readme.txt"}:
        return None
    if lower.endswith("_prompt.txt"):
        stem = name[: -len("_prompt.txt")]
    elif lower.endswith(".txt"):
        stem = path.stem
    else:
        return None
    match = PROBLEM_RE.match(stem)
    if not match:
        return None
    return match.group(1)


def _discover_prompt_paths(prompts_dir: Path) -> dict[str, Path]:
    by_problem: dict[str, Path] = {}

    # Prefer official dataset naming first.
    for path in sorted(prompts_dir.glob("*_prompt.txt")):
        problem_id = _prompt_problem_id(path)
        if not problem_id:
            continue
        by_problem.setdefault(problem_id, path)

    # Backward-compatible fallback for legacy local corpora.
    for path in sorted(prompts_dir.glob("*.txt")):
        if path.name.lower().endswith("_prompt.txt"):
            continue
        problem_id = _prompt_problem_id(path)
        if not problem_id:
            continue
        by_problem.setdefault(problem_id, path)

    return by_problem


def _discover_prompt_cases(
    *,
    prompts_dir: Path,
    dataset_dir: Path,
    only_problem: Iterable[str],
    max_problems: int,
    oracle_manifest: dict[str, dict[str, str]] | None = None,
) -> list[PromptCase]:
    requested = {str(item).strip() for item in only_problem if str(item).strip()}
    by_problem = _discover_prompt_paths(prompts_dir)
    if requested:
        by_problem = {problem_id: path for problem_id, path in by_problem.items() if problem_id in requested}

    cases: list[PromptCase] = []
    for problem_id in sorted(by_problem):
        if oracle_manifest and problem_id in oracle_manifest:
            entry = oracle_manifest[problem_id]
            test_sv = Path(entry["test_sv"]).expanduser()
            ref_sv = Path(entry["ref_sv"]).expanduser()
            if not test_sv.is_absolute():
                test_sv = (dataset_dir / test_sv).resolve()
            if not ref_sv.is_absolute():
                ref_sv = (dataset_dir / ref_sv).resolve()
            if not test_sv.exists() or not ref_sv.exists():
                raise RuntimeError(
                    f"Oracle manifest entry for {problem_id} points to missing files: "
                    f"test={test_sv}, ref={ref_sv}"
                )
        else:
            test_sv, ref_sv = _resolve_dataset_pair(dataset_dir, problem_id)
        cases.append(
            PromptCase(
                problem_id=problem_id,
                prompt_path=by_problem[problem_id],
                test_sv=test_sv,
                ref_sv=ref_sv,
            )
        )
    if max_problems > 0:
        cases = cases[:max_problems]
    if requested:
        found = {case.problem_id for case in cases}
        missing = sorted(requested - found)
        if missing:
            raise RuntimeError(f"Requested problem IDs not found in prompts/dataset: {', '.join(missing)}")
    if not cases:
        raise RuntimeError(f"No benchmark prompt cases found under {prompts_dir}.")
    return cases


def _summary_rows(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for raw in reader:
            if not raw:
                continue
            row: dict[str, Any] = {"problem_id": raw[0], "raw": raw}
            if len(raw) > 1:
                row["npass"] = raw[1]
            if len(raw) > 2:
                row["nsamples"] = raw[2]
            if len(raw) > 3:
                row["pass_rate"] = raw[3]
            if len(raw) > 4:
                row["failure_markers"] = raw[4:]
            rows.append(row)
    return rows


def _summary_metrics(summary_txt: Path) -> dict[str, int | float]:
    metrics: dict[str, int | float] = {}
    for raw in summary_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        match = SUMMARY_KV_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        value_raw = match.group(2)
        value = float(value_raw)
        if value.is_integer():
            metrics[key] = int(value)
        else:
            metrics[key] = value
    return metrics


def _write_internal_summary(
    *,
    out_dir: Path,
    run_label: str,
    sample_cfg: Dict[str, Any],
    summary_txt: Path,
    summary_csv: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _summary_rows(summary_csv)
    metrics = _summary_metrics(summary_txt)
    payload = {
        "run_label": run_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": sample_cfg,
        "official_artifacts": {
            "summary_txt": str(summary_txt),
            "summary_csv": str(summary_csv),
        },
        "aggregate": {
            "official_metrics": metrics,
            "row_count": len(rows),
        },
        "per_problem": rows,
    }
    (out_dir / "aggregate.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _find_summary_files(build_dir: Path) -> tuple[Path, Path]:
    summary_txt = build_dir / "summary.txt"
    summary_csv = build_dir / "summary.csv"
    if not summary_txt.exists() or not summary_csv.exists():
        raise RuntimeError(
            f"Official analysis artifacts not found under '{build_dir}'. "
            "Expected summary.txt and summary.csv."
        )
    return summary_txt, summary_csv


def _run_optional_failure_reports(root: Path, build_dir: Path, summary_csv: Path) -> None:
    report_scripts = [
        root / "scripts" / "count_failures.py",
        root / "scripts" / "count_failures_by_benchmark.py",
    ]
    for script in report_scripts:
        if not script.exists():
            continue
        out_path = build_dir / f"{script.stem}.txt"
        proc = _run_cmd(_script_cmd(script, [str(summary_csv)]), cwd=build_dir, timeout_s=120)
        if proc.returncode != 0:
            # Some framework scripts assume cwd contains summary.csv and take no args.
            proc = _run_cmd(_script_cmd(script, []), cwd=build_dir, timeout_s=120)
        text = (proc.stdout or "").strip()
        if proc.stderr:
            text = (text + "\n" + proc.stderr.strip()).strip()
        if not text:
            text = f"{script.name} exited with code {proc.returncode}"
        out_path.write_text(text + "\n", encoding="utf-8")


def _resolve_target_module_name(case: PromptCase, prompt_text: str) -> str:
    try:
        test_text = case.test_sv.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        test_text = ""
    inst_match = TOP_MODULE_INSTANCE_RE.search(test_text)
    if inst_match:
        return inst_match.group(1)

    named_match = MODULE_NAMED_RE.search(prompt_text)
    if named_match:
        return named_match.group(1)

    decl_match = MODULE_DECL_RE.search(prompt_text)
    if decl_match:
        return decl_match.group(1)
    return case.problem_id


def _resolve_target_interface(case: PromptCase) -> list[dict[str, Any]]:
    try:
        ref_text = case.ref_sv.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return []
    header_match = MODULE_HEADER_RE.search(ref_text)
    if not header_match:
        return []
    header = header_match.group(1)
    signals: list[dict[str, Any]] = []
    for match in MODULE_PORT_RE.finditer(header):
        direction = match.group(1).upper()
        width_token = (match.group(2) or "").strip()
        name = match.group(3)
        width: int | str = 1
        if width_token:
            inner = width_token[1:-1].strip()
            simple = re.match(r"(\d+)\s*:\s*0$", inner)
            if simple:
                width = int(simple.group(1)) + 1
            else:
                width = f"({inner})+1"
        signals.append({"name": name, "direction": direction, "width": width})
    return signals


def _width_from_range_token(width_token: str | None) -> int | str:
    text = str(width_token or "").strip()
    if not text:
        return 1
    inner = text[1:-1].strip() if text.startswith("[") and text.endswith("]") else text
    simple = re.match(r"(\d+)\s*:\s*0$", inner)
    if simple:
        return int(simple.group(1)) + 1
    return f"({inner})+1"


def _canonical_width(width: Any) -> int | str:
    if isinstance(width, int):
        return width
    if isinstance(width, float) and float(width).is_integer():
        return int(width)
    text = str(width).strip()
    if text.isdigit():
        return int(text)
    return re.sub(r"\s+", "", text)


def _extract_module_block(source: str, module_name: str) -> str | None:
    pattern = re.compile(MODULE_BLOCK_TEMPLATE.format(name=re.escape(module_name)), re.IGNORECASE | re.DOTALL)
    match = pattern.search(source)
    if not match:
        return None
    return match.group(0)


def _extract_ports_from_ansi_header(block: str, module_name: str) -> list[dict[str, Any]]:
    header_re = re.compile(
        rf"\bmodule\s+{re.escape(module_name)}\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    match = header_re.search(block)
    if not match:
        return []
    header = match.group(1)
    ports: list[dict[str, Any]] = []
    for item in MODULE_PORT_RE.finditer(header):
        ports.append(
            {
                "name": item.group(3),
                "direction": item.group(1).upper(),
                "width": _width_from_range_token(item.group(2)),
            }
        )
    return ports


def _extract_ports_from_body_decls(block: str) -> list[dict[str, Any]]:
    ports: list[dict[str, Any]] = []
    for match in BODY_PORT_DECL_RE.finditer(block):
        direction = match.group(1).upper()
        width = _width_from_range_token(match.group(2))
        names_blob = match.group(3)
        for raw_name in names_blob.split(","):
            token = raw_name.strip()
            if not token:
                continue
            token = token.split("=")[0].strip()
            token = re.sub(r"\[[^]]+\]", " ", token)
            parts = [part for part in token.split() if part]
            if not parts:
                continue
            name = parts[-1]
            if not IDENT_RE.fullmatch(name):
                continue
            ports.append({"name": name, "direction": direction, "width": width})
    return ports


def _extract_generated_interface(rtl_path: Path, module_name: str) -> list[dict[str, Any]]:
    source = rtl_path.read_text(encoding="utf-8", errors="ignore")
    block = _extract_module_block(source, module_name)
    if block is None:
        raise RuntimeError(f"Generated RTL does not define module '{module_name}' in {rtl_path}")
    ansi_ports = _extract_ports_from_ansi_header(block, module_name)
    if ansi_ports:
        return ansi_ports
    decl_ports = _extract_ports_from_body_decls(block)
    if decl_ports:
        return decl_ports
    raise RuntimeError(f"Unable to parse interface ports for module '{module_name}' in {rtl_path}")


def _assert_generated_interface_matches(
    *,
    rtl_path: Path,
    module_name: str,
    expected_signals: list[dict[str, Any]],
) -> None:
    actual_signals = _extract_generated_interface(rtl_path, module_name)
    expected_map = {
        str(sig["name"]): (str(sig["direction"]).upper(), _canonical_width(sig.get("width", 1)))
        for sig in expected_signals
    }
    actual_map = {
        str(sig["name"]): (str(sig["direction"]).upper(), _canonical_width(sig.get("width", 1)))
        for sig in actual_signals
    }

    missing = sorted(set(expected_map) - set(actual_map))
    extra = sorted(set(actual_map) - set(expected_map))
    mismatched = sorted(
        name
        for name in (set(expected_map) & set(actual_map))
        if expected_map[name] != actual_map[name]
    )
    if not missing and not extra and not mismatched:
        return

    details: list[str] = []
    if missing:
        details.append(f"missing ports: {', '.join(missing)}")
    if extra:
        details.append(f"extra ports: {', '.join(extra)}")
    if mismatched:
        formatted = ", ".join(
            f"{name} expected={expected_map[name]} actual={actual_map[name]}"
            for name in mismatched
        )
        details.append(f"mismatched ports: {formatted}")
    raise RuntimeError(
        f"Generated interface mismatch for module '{module_name}' in {rtl_path}: " + "; ".join(details)
    )


def _tracker_totals() -> dict[str, float]:
    totals = get_tracker().get_totals()
    return {
        "prompt_tokens": float(totals.get("prompt_tokens", 0) or 0),
        "completion_tokens": float(totals.get("completion_tokens", 0) or 0),
        "total_tokens": float(totals.get("total_tokens", 0) or 0),
        "estimated_cost_usd": float(totals.get("estimated_cost_usd", 0.0) or 0.0),
    }


def _totals_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {
        "prompt_tokens": max(0.0, after["prompt_tokens"] - before["prompt_tokens"]),
        "completion_tokens": max(0.0, after["completion_tokens"] - before["completion_tokens"]),
        "total_tokens": max(0.0, after["total_tokens"] - before["total_tokens"]),
        "estimated_cost_usd": max(0.0, after["estimated_cost_usd"] - before["estimated_cost_usd"]),
    }


def _write_generate_log(
    *,
    path: Path,
    status: TaskStatus | str,
    prompt_tokens: float,
    resp_tokens: float,
    cost_usd: float,
    details: str,
) -> None:
    if isinstance(status, TaskStatus):
        status_text = status.value
    else:
        status_text = str(status)
    lines = [
        f"status = {status_text}",
        f"prompt_tokens = {int(prompt_tokens)}",
        f"resp_tokens = {int(resp_tokens)}",
        f"cost = {cost_usd:.6f}",
    ]
    detail_text = (details or "").strip()
    if detail_text:
        lines.append(detail_text)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reset_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _resolve_generated_rtl_path(design_context_path: Path, generated_root: Path, preferred_node: str) -> Path:
    payload = json.loads(design_context_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), dict) else {}

    selected: str | None = None
    if preferred_node in nodes:
        selected = preferred_node
    else:
        top_module = str(payload.get("top_module") or "")
        if top_module in nodes:
            selected = top_module
        elif nodes:
            selected = next(iter(nodes.keys()))

    if selected:
        node = nodes.get(selected, {})
        rtl_rel = str(node.get("rtl_file") or "").strip()
        if rtl_rel:
            rtl_path = (generated_root / rtl_rel).resolve()
            if rtl_path.exists():
                return rtl_path

    preferred = (generated_root / "rtl" / f"{preferred_node}.sv").resolve()
    if preferred.exists():
        return preferred

    fallback = sorted((generated_root / "rtl").glob("*.sv"))
    if fallback:
        return fallback[0].resolve()

    raise RuntimeError(f"No generated RTL file found under {generated_root}")


def _snapshot_pipeline_trace(
    *,
    sample_dir: Path,
    sample_index: int,
    generated_root: Path,
    task_memory_root: Path,
    metadata: dict[str, Any],
) -> None:
    trace_root = sample_dir / f"pipeline_sample{sample_index:02d}"
    _copy_tree(generated_root, trace_root / "generated")
    _copy_tree(task_memory_root, trace_root / "task_memory")
    (trace_root / "orchestrator_meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


@contextlib.contextmanager
def _isolated_task_memory(task_memory_root: Path):
    backup_path = task_memory_root.with_name(f"{task_memory_root.name}.benchmark_backup")
    if backup_path.exists():
        shutil.rmtree(backup_path, ignore_errors=True)
    had_original = task_memory_root.exists()
    if had_original:
        task_memory_root.rename(backup_path)
    task_memory_root.mkdir(parents=True, exist_ok=True)
    try:
        yield
    finally:
        shutil.rmtree(task_memory_root, ignore_errors=True)
        if had_original and backup_path.exists():
            backup_path.rename(task_memory_root)
        elif backup_path.exists():
            shutil.rmtree(backup_path, ignore_errors=True)


def _ensure_broker_connection(params: pika.ConnectionParameters) -> None:
    try:
        conn = pika.BlockingConnection(params)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Benchmark orchestrated mode requires RabbitMQ connectivity. "
            f"Failed to connect to broker: {exc}"
        ) from exc


def _purge_benchmark_queues(params: pika.ConnectionParameters) -> None:
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        declare_task_topology(ch, include_legacy_bindings=True)
        for queue_name in _BENCHMARK_QUEUE_PURGE_LIST:
            try:
                ch.queue_purge(queue=queue_name)
            except Exception:
                continue


def _generate_one_sample_legacy(
    *,
    worker: ImplementationWorker,
    case: PromptCase,
    sample_index: int,
    sample_dir: Path,
) -> None:
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_name = f"{case.problem_id}_sample{sample_index:02d}"
    sample_sv = sample_dir / f"{sample_name}.sv"
    generate_log_path = sample_dir / f"{sample_name}-sv-generate.log"

    execution_policy = {
        "preset": "benchmark",
        "spec_profile": "benchmark",
        "verification_profile": "oracle_compare",
        "allow_repair_loop": False,
        "benchmark_mode": True,
    }

    with tempfile.TemporaryDirectory(prefix=f"{case.problem_id}_") as tmp:
        tmp_root = Path(tmp)
        spec_dir = tmp_root / "specs"
        out_dir = tmp_root / "generated"
        prev_spec_dir = spec_flow.SPEC_DIR
        try:
            spec_flow.SPEC_DIR = spec_dir
            prompt_text = case.prompt_path.read_text(encoding="utf-8", errors="ignore")
            target_module_name = _resolve_target_module_name(case, prompt_text)
            spec_flow.collect_specs_from_text(
                module_name=target_module_name,
                spec_text=prompt_text,
                interactive=False,
                spec_profile="benchmark",
            )
            planner.generate_from_specs(
                spec_dir=spec_dir,
                out_dir=out_dir,
                execution_policy=execution_policy,
            )
            design_context_path = out_dir / "design_context.json"
            if not design_context_path.exists():
                raise RuntimeError("Planner did not produce design_context.json")
            context_payload = json.loads(design_context_path.read_text(encoding="utf-8"))
            nodes = context_payload.get("nodes") if isinstance(context_payload.get("nodes"), dict) else {}
            if not nodes:
                raise RuntimeError("Planner produced empty design context nodes.")
            top_module = str(context_payload.get("top_module") or "")
            if top_module not in nodes:
                top_module = next(iter(nodes.keys()))
            task_ctx = DemoContextBuilder(design_context_path, out_dir).build(top_module)
            task_ctx["execution_policy"] = execution_policy
            task_ctx["node_id"] = target_module_name
            ref_interface = _resolve_target_interface(case)
            if ref_interface:
                task_ctx["interface"] = {"signals": ref_interface}
            task_ctx["clocking"] = {}
            task_ctx["demo_behavior"] = prompt_text
            result = worker.handle_task(
                TaskMessage(
                    entity_type=EntityType.REASONING,
                    task_type=AgentType.IMPLEMENTATION,
                    context=task_ctx,
                )
            )
            rtl_path = Path(task_ctx["rtl_path"])
            if result.status is TaskStatus.SUCCESS and rtl_path.exists():
                shutil.copy2(rtl_path, sample_sv)
            else:
                sample_sv.write_text(
                    f"module {target_module_name}();\n"
                    "// generation failed; placeholder for harness compile\n"
                    "endmodule\n",
                    encoding="utf-8",
                )
            _write_generate_log(
                path=generate_log_path,
                status=result.status,
                prompt_tokens=0,
                resp_tokens=0,
                cost_usd=0.0,
                details=result.log_output or "",
            )
            return
        finally:
            spec_flow.SPEC_DIR = prev_spec_dir


def _generate_one_sample_orchestrated(
    *,
    connection_params: pika.ConnectionParameters,
    case: PromptCase,
    sample_index: int,
    sample_dir: Path,
    pipeline_timeout_s: float,
    execution_policy: dict[str, Any],
    task_memory_root: Path,
) -> None:
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_name = f"{case.problem_id}_sample{sample_index:02d}"
    sample_sv = sample_dir / f"{sample_name}.sv"
    generate_log_path = sample_dir / f"{sample_name}-sv-generate.log"

    prompt_text = case.prompt_path.read_text(encoding="utf-8", errors="ignore")
    target_module_name = _resolve_target_module_name(case, prompt_text)
    expected_interface = _resolve_target_interface(case)

    before = _tracker_totals()
    pipeline_status = TaskStatus.FAILURE
    detail_message = ""

    with tempfile.TemporaryDirectory(prefix=f"{case.problem_id}_orchestrated_") as tmp:
        runtime_root = Path(tmp)
        spec_dir = runtime_root / "specs"
        generated_root = runtime_root / "generated"
        run_routing = create_run_routing()
        metadata: dict[str, Any] = {
            "problem_id": case.problem_id,
            "sample_index": sample_index,
            "target_module": target_module_name,
            "run_id": run_routing.run_id,
            "results_routing_key": run_routing.results_routing_key,
            "execution_policy": execution_policy,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_timeout_s": pipeline_timeout_s,
        }

        prev_spec_dir = spec_flow.SPEC_DIR
        _reset_dir(task_memory_root)

        try:
            spec_flow.SPEC_DIR = spec_dir
            spec_flow.collect_specs_from_text(
                module_name=target_module_name,
                spec_text=prompt_text,
                interactive=False,
                spec_profile="benchmark",
            )
            planner.generate_from_specs(
                spec_dir=spec_dir,
                out_dir=generated_root,
                execution_policy=execution_policy,
            )

            design_context_path = generated_root / "design_context.json"
            dag_path = generated_root / "dag.json"
            if not design_context_path.exists() or not dag_path.exists():
                raise RuntimeError("Planner did not produce design_context.json and dag.json")

            final_states = DemoOrchestrator(
                connection_params,
                design_context_path,
                dag_path,
                generated_root,
                task_memory_root,
                run_id=run_routing.run_id,
                results_routing_key=run_routing.results_routing_key,
                allow_repair_loop=True,
                execution_policy=execution_policy,
            ).run(timeout_s=pipeline_timeout_s)
            failed_nodes = sorted(node_id for node_id, state in final_states.items() if state != "DONE")
            if failed_nodes:
                raise RuntimeError(
                    "Pipeline did not complete successfully for all nodes: "
                    + ", ".join(f"{node_id}={final_states[node_id]}" for node_id in failed_nodes)
                )

            rtl_path = _resolve_generated_rtl_path(design_context_path, generated_root, target_module_name)
            if expected_interface:
                _assert_generated_interface_matches(
                    rtl_path=rtl_path,
                    module_name=target_module_name,
                    expected_signals=expected_interface,
                )
            shutil.copy2(rtl_path, sample_sv)
            pipeline_status = TaskStatus.SUCCESS
            detail_message = (
                f"pipeline_status = success\n"
                f"run_id = {run_routing.run_id}\n"
                f"rtl_source = {rtl_path}"
            )
            metadata["rtl_source"] = str(rtl_path)
        except Exception as exc:  # noqa: BLE001
            detail_message = (
                f"pipeline_status = failure\n"
                f"run_id = {run_routing.run_id}\n"
                f"error = {exc}"
            )
            metadata["error"] = str(exc)
            raise RuntimeError(
                f"Orchestrated benchmark generation failed for {case.problem_id} sample {sample_index:02d}: {exc}"
            ) from exc
        finally:
            spec_flow.SPEC_DIR = prev_spec_dir
            after = _tracker_totals()
            delta = _totals_delta(before, after)
            _write_generate_log(
                path=generate_log_path,
                status=pipeline_status,
                prompt_tokens=delta["prompt_tokens"],
                resp_tokens=delta["completion_tokens"],
                cost_usd=delta["estimated_cost_usd"],
                details=detail_message,
            )
            metadata.update(
                {
                    "status": pipeline_status.value,
                    "prompt_tokens": int(delta["prompt_tokens"]),
                    "resp_tokens": int(delta["completion_tokens"]),
                    "total_tokens": int(delta["total_tokens"]),
                    "estimated_cost_usd": round(delta["estimated_cost_usd"], 6),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _snapshot_pipeline_trace(
                sample_dir=sample_dir,
                sample_index=sample_index,
                generated_root=generated_root,
                task_memory_root=task_memory_root,
                metadata=metadata,
            )


def _run_sample_test(
    *,
    case: PromptCase,
    sample_index: int,
    sample_dir: Path,
    iverilog_bin: str,
    vvp_bin: str,
) -> None:
    sample_name = f"{case.problem_id}_sample{sample_index:02d}"
    sample_sv = sample_dir / f"{sample_name}.sv"
    sample_bin = sample_dir / sample_name
    iv_log_path = sample_dir / f"{sample_name}-sv-iv-test.log"
    compile_cmd = [
        iverilog_bin,
        "-Wall",
        "-Winfloop",
        "-Wno-timescale",
        "-g2012",
        "-s",
        "tb",
        "-o",
        str(sample_bin),
        str(sample_sv),
        str(case.test_sv),
        str(case.ref_sv),
    ]
    compile_proc = _run_cmd(
        compile_cmd,
        cwd=sample_dir,
        timeout_s=180,
    )
    log_chunks: list[str] = []
    compile_output = _merge_output(compile_proc.stdout, compile_proc.stderr)
    if compile_output:
        log_chunks.append(compile_output)
    if compile_proc.returncode == 0:
        try:
            run_proc = _run_cmd([vvp_bin, str(sample_bin)], cwd=sample_dir, timeout_s=30)
            run_output = _merge_output(run_proc.stdout, run_proc.stderr)
            if run_output:
                log_chunks.append(run_output)
            if run_proc.returncode != 0 and not run_output:
                log_chunks.append(f"vvp exited with code {run_proc.returncode}")
        except subprocess.TimeoutExpired as exc:
            timeout_output = _merge_output(exc.stdout, exc.stderr)
            if timeout_output:
                log_chunks.append(timeout_output)
            log_chunks.append("TIMEOUT")
    if not log_chunks:
        log_chunks.append(f"iverilog exited with code {compile_proc.returncode}")
    iv_log_path.write_text("\n".join(log_chunks) + "\n", encoding="utf-8")


def _run_official_analyze(root: Path, build_dir: Path) -> tuple[Path, Path]:
    summary_csv = build_dir / "summary.csv"
    summary_txt = build_dir / "summary.txt"
    sv_iv_analyze = root / "scripts" / "sv-iv-analyze"
    proc = _run_cmd(
        _script_cmd(sv_iv_analyze, [f"--csv={summary_csv.name}"]),
        cwd=build_dir,
        timeout_s=180,
    )
    output = (proc.stdout or "").strip()
    if proc.stderr:
        output = (output + "\n" + proc.stderr.strip()).strip()
    summary_txt.write_text((output + "\n") if output else "", encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"Official analyzer failed with exit code {proc.returncode}. See {summary_txt}")
    if not summary_csv.exists():
        raise RuntimeError(f"Official analyzer did not generate summary.csv under {build_dir}")
    return summary_txt, summary_csv


def _run_mode(
    *,
    root: Path,
    out_dir: Path,
    cases: list[PromptCase],
    sample_cfg: dict[str, Any],
    run_label: str,
    iverilog_bin: str,
    vvp_bin: str,
    legacy_lightweight: bool,
    pipeline_timeout_s: float,
) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_cfg = get_runtime_config().model_copy(deep=True)
    run_cfg = baseline_cfg.model_copy(deep=True)
    run_cfg.llm.temperature = float(sample_cfg["temperature"])
    run_cfg.llm.top_p = float(sample_cfg["top_p"])
    set_runtime_config(run_cfg)

    task_memory_root = Path("artifacts/task_memory").resolve()
    workers: list[threading.Thread] = []
    stop_event: threading.Event | None = None

    try:
        if legacy_lightweight:
            worker = ImplementationWorker(connection_params=None, stop_event=threading.Event())
            if not worker.gateway:
                raise RuntimeError(
                    "Implementation worker LLM gateway unavailable for benchmark generation. "
                    "Set provider credentials (e.g., OPENAI_API_KEY) and ensure llm.enabled is true."
                )
        else:
            connection_params = connection_params_from_config()
            _ensure_broker_connection(connection_params)
            _purge_benchmark_queues(connection_params)
            stop_event = threading.Event()
            workers = start_workers(connection_params, stop_event)

        n_samples = int(sample_cfg["n"])
        execution_policy = {
            "preset": "benchmark",
            "spec_profile": "benchmark",
            "verification_profile": "oracle_compare",
            "allow_repair_loop": True,
            "benchmark_mode": True,
            "debug_max_retries": int(get_runtime_config().debug.max_retries),
        }

        with _isolated_task_memory(task_memory_root):
            for case in cases:
                sample_dir = out_dir / case.problem_id
                for sample_index in range(1, n_samples + 1):
                    if legacy_lightweight:
                        _generate_one_sample_legacy(
                            worker=worker,
                            case=case,
                            sample_index=sample_index,
                            sample_dir=sample_dir,
                        )
                    else:
                        _generate_one_sample_orchestrated(
                            connection_params=connection_params,
                            case=case,
                            sample_index=sample_index,
                            sample_dir=sample_dir,
                            pipeline_timeout_s=pipeline_timeout_s,
                            execution_policy=execution_policy,
                            task_memory_root=task_memory_root,
                        )

                    _run_sample_test(
                        case=case,
                        sample_index=sample_index,
                        sample_dir=sample_dir,
                        iverilog_bin=iverilog_bin,
                        vvp_bin=vvp_bin,
                    )

        summary_txt, summary_csv = _run_official_analyze(root, out_dir)
        _run_optional_failure_reports(root, out_dir, summary_csv)
        _write_internal_summary(
            out_dir=out_dir,
            run_label=run_label,
            sample_cfg=sample_cfg,
            summary_txt=summary_txt,
            summary_csv=summary_csv,
        )
    finally:
        if workers and stop_event is not None:
            stop_workers(workers, stop_event)
        set_runtime_config(baseline_cfg)


def run_from_args(args: argparse.Namespace) -> None:
    runtime_cfg = get_runtime_config()
    benchmark_cfg = runtime_cfg.benchmark
    root = Path(benchmark_cfg.verilog_eval_root).resolve()
    prompts_dir = Path(benchmark_cfg.prompts_dir).resolve()
    output_root = Path(benchmark_cfg.output_root).resolve()

    dataset_dir = _ensure_framework(root)
    if not prompts_dir.exists():
        raise RuntimeError(f"Benchmark prompt directory not found: {prompts_dir}")
    if not _has_langchain_schema():
        raise RuntimeError(
            "Missing Python dependency 'langchain.schema' required by VerilogEval sv-iv-analyze. "
            "Install with: poetry run pip install 'langchain<0.2'"
        )

    if args.build_dir:
        build_dir = Path(args.build_dir).resolve()
        summary_txt, summary_csv = _find_summary_files(build_dir)
        _write_internal_summary(
            out_dir=build_dir,
            run_label="analyze_only",
            sample_cfg={},
            summary_txt=summary_txt,
            summary_csv=summary_csv,
        )
        print(f"Benchmark analysis complete: {build_dir / 'aggregate.json'}")
        return

    verilator_bin = _resolve_tool(runtime_cfg.tools.verilator_path, "verilator")
    iverilog_bin = _resolve_tool(runtime_cfg.tools.iverilog_path, "iverilog")
    vvp_bin = _resolve_tool(runtime_cfg.tools.vvp_path, "vvp")

    if not args.legacy_lightweight and not verilator_bin:
        raise RuntimeError(
            "Orchestrated benchmark mode requires verilator on PATH "
            "(or configured in tools.verilator_path)."
        )
    if not iverilog_bin or not vvp_bin:
        raise RuntimeError(
            "Benchmark runs require both iverilog and vvp on PATH (or configured in tools.iverilog_path/tools.vvp_path)."
        )

    if not args.legacy_lightweight:
        _ensure_broker_connection(connection_params_from_config())

    oracle_manifest: dict[str, dict[str, str]] | None = None
    if benchmark_cfg.oracle_manifest:
        oracle_manifest = _load_oracle_manifest(Path(benchmark_cfg.oracle_manifest).resolve())

    cases = _discover_prompt_cases(
        prompts_dir=prompts_dir,
        dataset_dir=dataset_dir,
        only_problem=args.only_problem or [],
        max_problems=max(0, int(args.max_problems or 0)),
        oracle_manifest=oracle_manifest,
    )
    canonical_cfg = {
        "n": int(benchmark_cfg.canonical.n),
        "temperature": float(benchmark_cfg.canonical.temperature),
        "top_p": float(benchmark_cfg.canonical.top_p),
    }
    canonical_dir = output_root / "canonical"
    _run_mode(
        root=root,
        out_dir=canonical_dir,
        cases=cases,
        sample_cfg=canonical_cfg,
        run_label="canonical",
        iverilog_bin=iverilog_bin,
        vvp_bin=vvp_bin,
        legacy_lightweight=bool(args.legacy_lightweight),
        pipeline_timeout_s=float(args.pipeline_timeout),
    )
    print(f"Canonical benchmark complete: {canonical_dir / 'aggregate.json'}")

    if args.sampled:
        sampled_cfg = {
            "n": int(benchmark_cfg.sampled.n),
            "temperature": float(benchmark_cfg.sampled.temperature),
            "top_p": float(benchmark_cfg.sampled.top_p),
        }
        sampled_dir = output_root / "sampled"
        _run_mode(
            root=root,
            out_dir=sampled_dir,
            cases=cases,
            sample_cfg=sampled_cfg,
            run_label="sampled",
            iverilog_bin=iverilog_bin,
            vvp_bin=vvp_bin,
            legacy_lightweight=bool(args.legacy_lightweight),
            pipeline_timeout_s=float(args.pipeline_timeout),
        )
        print(f"Sampled benchmark complete: {sampled_dir / 'aggregate.json'}")
