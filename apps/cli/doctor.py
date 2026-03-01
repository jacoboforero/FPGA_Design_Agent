"""
CLI preflight checks for configuration and local toolchain readiness.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from core.runtime.config import DEFAULT_CONFIG_PATH, RuntimeConfig, get_runtime_config


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "PASS"


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


def run_checks(config: RuntimeConfig, *, force_benchmark: bool = False) -> List[CheckResult]:
    results: List[CheckResult] = []
    preset = config.resolved_preset

    results.append(
        CheckResult(
            name="runtime_config",
            status="PASS",
            message=(
                f"preset={config.active_preset} "
                f"(spec_profile={preset.spec_profile}, verification_profile={preset.verification_profile})"
            ),
        )
    )

    if config.llm.enabled:
        provider = str(config.llm.provider or "").strip().lower()
        if provider == "openai":
            if os.getenv("OPENAI_API_KEY"):
                results.append(CheckResult("llm_credentials", "PASS", "OPENAI_API_KEY present."))
            else:
                results.append(CheckResult("llm_credentials", "FAIL", "OPENAI_API_KEY missing."))
        elif provider == "groq":
            if os.getenv("GROQ_API_KEY"):
                results.append(CheckResult("llm_credentials", "PASS", "GROQ_API_KEY present."))
            else:
                results.append(CheckResult("llm_credentials", "FAIL", "GROQ_API_KEY missing."))
        else:
            results.append(
                CheckResult(
                    "llm_credentials",
                    "WARN",
                    f"Unsupported provider '{provider}'. Doctor cannot verify credentials.",
                )
            )
    else:
        results.append(CheckResult("llm_credentials", "WARN", "LLM calls disabled (llm.enabled=false)."))

    verilator = _resolve_tool(config.tools.verilator_path, "verilator")
    iverilog = _resolve_tool(config.tools.iverilog_path, "iverilog")
    vvp = _resolve_tool(config.tools.vvp_path, "vvp")

    if verilator:
        results.append(CheckResult("tool_verilator", "PASS", f"found at {verilator}"))
        try:
            probe = subprocess.run([verilator, "--help"], capture_output=True, text=True, timeout=5)
            output = (probe.stdout or "") + (probe.stderr or "")
            if "--quiet" in output:
                results.append(CheckResult("verilator_quiet_flag", "PASS", "supports --quiet"))
            else:
                results.append(CheckResult("verilator_quiet_flag", "WARN", "does not advertise --quiet"))
        except Exception as exc:  # noqa: BLE001
            results.append(CheckResult("verilator_quiet_flag", "WARN", f"could not probe --quiet support: {exc}"))
    else:
        results.append(CheckResult("tool_verilator", "WARN", "verilator not found"))

    if iverilog:
        results.append(CheckResult("tool_iverilog", "PASS", f"found at {iverilog}"))
    else:
        results.append(CheckResult("tool_iverilog", "WARN", "iverilog not found"))

    if vvp:
        results.append(CheckResult("tool_vvp", "PASS", f"found at {vvp}"))
    else:
        results.append(CheckResult("tool_vvp", "WARN", "vvp not found"))

    benchmark_needed = bool(force_benchmark or preset.benchmark_mode)
    if benchmark_needed:
        root = Path(config.benchmark.verilog_eval_root).resolve()
        required = [
            root / "scripts" / "sv-iv-analyze",
            root / "Makefile.in",
            root / "dataset_spec-to-rtl",
        ]
        missing = [path for path in required if not path.exists()]
        if missing:
            results.append(
                CheckResult(
                    "benchmark_framework",
                    "FAIL",
                    "missing: " + ", ".join(str(path) for path in missing),
                )
            )
        else:
            results.append(CheckResult("benchmark_framework", "PASS", f"ready at {root}"))

        prompts_dir = Path(config.benchmark.prompts_dir).resolve()
        if prompts_dir.exists():
            n_prompts = len(list(prompts_dir.glob("*.txt")))
            results.append(CheckResult("benchmark_prompts", "PASS", f"{n_prompts} prompt files under {prompts_dir}"))
        else:
            results.append(CheckResult("benchmark_prompts", "FAIL", f"missing prompts dir {prompts_dir}"))

        if iverilog and vvp:
            results.append(CheckResult("benchmark_sim_tools", "PASS", "iverilog/vvp available for benchmark compile/run"))
        else:
            results.append(CheckResult("benchmark_sim_tools", "FAIL", "iverilog and vvp are required for benchmark runs"))

        if _has_langchain_schema():
            results.append(CheckResult("benchmark_analyzer_deps", "PASS", "langchain.schema available"))
        else:
            results.append(
                CheckResult(
                    "benchmark_analyzer_deps",
                    "FAIL",
                    "missing langchain.schema required by verilog_eval/scripts/sv-iv-analyze (install langchain<0.2)",
                )
            )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run preflight checks for local runtime readiness.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to runtime YAML config.")
    parser.add_argument("--preset", help="Preset override for checks.")
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Force benchmark-specific checks even if the selected preset is not benchmark.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings in addition to failures.",
    )
    return parser


def run_from_args(args: argparse.Namespace) -> int:
    config = get_runtime_config()
    results = run_checks(config, force_benchmark=bool(args.benchmark))

    pass_count = sum(1 for item in results if item.status == "PASS")
    warn_count = sum(1 for item in results if item.status == "WARN")
    fail_count = sum(1 for item in results if item.status == "FAIL")

    for item in results:
        print(f"[{item.status}] {item.name}: {item.message}")

    print(
        "\nDoctor summary: "
        f"{pass_count} pass, {warn_count} warn, {fail_count} fail "
        f"(preset={config.active_preset})"
    )
    if fail_count > 0:
        return 1
    if args.strict and warn_count > 0:
        return 1
    return 0
