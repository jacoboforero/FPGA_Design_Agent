# Benchmark Methodology

## Purpose
Define benchmark execution and scoring policy for VerilogEval-compatible runs.

## Audience
Engineers running or reviewing benchmark results.

## Scope
Benchmark flow, profiles, and artifact expectations.

## Profiles
- Canonical: `n=1`, low-temperature deterministic setting
- Sampled: configurable multi-sample setting

## Execution (from repo root)
```bash
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark
PYTHONPATH=. python3 apps/cli/cli.py benchmark --preset benchmark --sampled
```

## Expected Outputs
- Official-style benchmark summaries
- Sample-level compile/run logs
- Internal aggregate report derived from benchmark outputs

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/cli/run_verilog_eval.py`
- `/home/jacobo/school/FPGA_Design_Agent/config/runtime.yaml`

## Related Docs
- [workflows/benchmark-run.md](./workflows/benchmark-run.md)
- [cli.md](./cli.md)
