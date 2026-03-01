"""
VerilogEval runner with official analyzer parity.

This command generates RTL with this project pipeline and delegates scoring to
the official VerilogEval scripts/artifacts (`summary.txt`, `summary.csv`).
"""
from __future__ import annotations

import argparse
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

from agents.implementation.worker import ImplementationWorker
from apps.cli import spec_flow
from core.runtime.config import DEFAULT_CONFIG_PATH, get_runtime_config, set_runtime_config
from core.schemas.contracts import AgentType, EntityType, TaskMessage, TaskStatus
from orchestrator import planner
from orchestrator.context_builder import DemoContextBuilder

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


def _discover_prompt_cases(
    *,
    prompts_dir: Path,
    dataset_dir: Path,
    only_problem: Iterable[str],
    max_problems: int,
    oracle_manifest: dict[str, dict[str, str]] | None = None,
) -> list[PromptCase]:
    requested = {str(item).strip() for item in only_problem if str(item).strip()}
    prompt_files = sorted(prompts_dir.glob("*.txt"))
    by_problem: dict[str, Path] = {}
    for path in prompt_files:
        match = PROBLEM_RE.match(path.stem)
        if not match:
            continue
        problem_id = match.group(1)
        if requested and problem_id not in requested:
            continue
        by_problem.setdefault(problem_id, path)

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


def _generate_one_sample(
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
            gen_lines = [
                f"status = {result.status.value}",
                "prompt_tokens = 0",
                "response_tokens = 0",
                "cost = $0.000000",
                (result.log_output or "").strip(),
            ]
            generate_log_path.write_text("\n".join(line for line in gen_lines if line) + "\n", encoding="utf-8")
            return
        finally:
            spec_flow.SPEC_DIR = prev_spec_dir


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
) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_cfg = get_runtime_config().model_copy(deep=True)
    run_cfg = baseline_cfg.model_copy(deep=True)
    run_cfg.llm.temperature = float(sample_cfg["temperature"])
    run_cfg.llm.top_p = float(sample_cfg["top_p"])
    set_runtime_config(run_cfg)
    try:
        worker = ImplementationWorker(connection_params=None, stop_event=threading.Event())
        if not worker.gateway:
            raise RuntimeError(
                "Implementation worker LLM gateway unavailable for benchmark generation. "
                "Set provider credentials (e.g., OPENAI_API_KEY) and ensure llm.enabled is true."
            )
        n_samples = int(sample_cfg["n"])
        for case in cases:
            sample_dir = out_dir / case.problem_id
            for sample_index in range(1, n_samples + 1):
                _generate_one_sample(worker=worker, case=case, sample_index=sample_index, sample_dir=sample_dir)
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
        set_runtime_config(baseline_cfg)


def run_from_args(args: argparse.Namespace) -> None:
    runtime_cfg = get_runtime_config()
    benchmark_cfg = runtime_cfg.benchmark
    root = Path(benchmark_cfg.verilog_eval_root).resolve()
    prompts_dir = Path(benchmark_cfg.prompts_dir).resolve()
    output_root = Path(benchmark_cfg.output_root).resolve()

    dataset_dir = _ensure_framework(root)
    if not prompts_dir.exists():
        raise RuntimeError(f"Processed prompt directory not found: {prompts_dir}")
    if not _has_langchain_schema():
        raise RuntimeError(
            "Missing Python dependency 'langchain.schema' required by verilog_eval/scripts/sv-iv-analyze. "
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

    iverilog_bin = _resolve_tool(runtime_cfg.tools.iverilog_path, "iverilog")
    vvp_bin = _resolve_tool(runtime_cfg.tools.vvp_path, "vvp")
    if not iverilog_bin or not vvp_bin:
        raise RuntimeError(
            "Benchmark runs require both iverilog and vvp on PATH (or configured in tools.iverilog_path/tools.vvp_path)."
        )

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
        )
        print(f"Sampled benchmark complete: {sampled_dir / 'aggregate.json'}")
