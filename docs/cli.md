# CLI

Last verified against runtime behavior: March 8, 2026.

`apps/cli/cli.py` is the main entrypoint for full runs, doctor checks, and benchmark runs.

This command surface has two user modes:
- hardware-engineering mode (`cli.py` full flow) for design work,
- research mode (`cli.py benchmark`) for scripted evaluation.

## What This Page Is For
Use this page to choose the right CLI entrypoint quickly and avoid running the wrong workflow.

## What This Page Is Not For
- It is not the complete engineer runbook; use [workflows/interactive-run.md](./workflows/interactive-run.md).
- It is not the complete benchmark runbook; use [workflows/benchmark-run.md](./workflows/benchmark-run.md).

## Command Decision Matrix
Use this table first when deciding what to run.

| Goal | Primary Command | Notes |
| --- | --- | --- |
| Run full engineer flow interactively | `PYTHONPATH=. python3 apps/cli/cli.py --preset engineer_fast` | Includes spec collection, planning gate, orchestrated execution. |
| Validate environment before engineer run | `PYTHONPATH=. python3 apps/cli/cli.py doctor --preset engineer_fast` | Verifies credentials/tools/broker readiness for selected preset behavior. |
| Run benchmark generation/scoring | `PYTHONPATH=. python3 apps/cli/cli.py benchmark run --preset benchmark --campaign <name>` | Produces run-manifest + canonical mode outputs. |
| List benchmark cases before running | `PYTHONPATH=. python3 apps/cli/cli.py benchmark list-problems --preset benchmark` | Validates prompt/discovery coverage quickly. |
| Plan benchmark run without execution | `PYTHONPATH=. python3 apps/cli/cli.py benchmark run --preset benchmark --campaign <name> --dry-run` | Non-destructive plan preview. |
| Rebuild local benchmark aggregate from existing official outputs | `PYTHONPATH=. python3 apps/cli/cli.py benchmark analyze --build-dir <mode_dir>` | Requires existing `summary.txt` and `summary.csv`. |
| Compare two benchmark mode outputs | `PYTHONPATH=. python3 apps/cli/cli.py benchmark compare --left-dir <mode_a> --right-dir <mode_b>` | Structured delta report for pass-rate and metrics. |
| Execute many benchmark runs from YAML | `python3 scripts/run_benchmark_campaign.py --campaign-file <path>` | Research campaign automation utility. |

## Common Commands
From repo root:

```bash
PYTHONPATH=. python3 apps/cli/cli.py --config config/runtime.yaml --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py doctor --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py benchmark run --preset benchmark --campaign smoke
```

Optional aliases:

```bash
PYTHONPATH=. python3 apps/cli/cli.py run --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py full --preset engineer_fast
```

## Full Interactive Flow (Engineer Path)
1. Collect specs (interactive by default unless `--spec-file` is provided).
2. Run planner.
3. Display generated DAG summary.
4. Ask `Proceed to execution?` unless `--yes` is passed.
5. Execute orchestrated pipeline and print generated RTL paths/content.

## Benchmark Subcommands (Research Path)
`benchmark` mode subcommands:
- `run`
- `analyze`
- `compare`
- `list-problems`

Behavior note:
- `cli.py benchmark` without subcommand defaults to `run`.

## Useful Flags
Engineer flow flags:
- `--timeout`: pipeline timeout in seconds (`0` disables timeout).
- `--spec-file`: run non-interactively from a spec file.
- `--direct-spec`: parse structured L1-L5 directly from spec file.
- `--run-name`: label observability artifacts.
- `--narrative-mode {llm,deterministic,off}`: control execution narration.

Benchmark flow flags:
- `--campaign`, `--run-id`, `--run-dir`: control run identity and run directory layout.
- `--sampled`, `--legacy-lightweight`, `--pipeline-timeout`: benchmark execution behavior.
- `--resume`, `--overwrite`, `--dry-run`: run safety and controllability.
- `--max-problems`, `--only-problem`: discovery filtering controls.
- `--purge-queues`: optional benchmark queue purge.

## Runtime Ownership Notes
- Runtime behavior comes from YAML config (`config/runtime.yaml` and selected preset).
- API keys and secrets remain environment-driven.
- Prefer explicit presets and run labels for reproducibility.

## Related Code
- `apps/cli/cli.py`
- `apps/cli/spec_flow.py`
- `apps/cli/doctor.py`
- `apps/cli/run_verilog_eval.py`
- `scripts/run_benchmark_campaign.py`
