# Demo Script

## 1. Homebrew Install

Run from repo root:

```bash
cd "/Users/jacoboforero/Desktop/School/SD1 Proj"
brew uninstall --ignore-dependencies --force mhd || true
brew untap local/mhd-demo || true
brew services start rabbitmq
bash scripts/test_homebrew_install.sh
```

## 2. Switch To Installed Demo Workspace

```bash
cd "/Users/jacoboforero/Desktop/mhd-homebrew-demo"
```

## 3. Show Flags And Help

```bash
mhd --help
mhd benchmark --help
mhd doctor --config config/runtime.yaml
```

## 4. Basic 3-Bit Counter Run

```bash
mhd --config config/runtime.yaml --spec-file 01_counter3_basic.txt --yes --narrative-mode deterministic --run-name demo_counter_det
```

## 5. Show Different Narrative Modes

```bash
mhd --config config/runtime.yaml --spec-file 01_counter3_basic.txt --yes --narrative-mode off --run-name demo_counter_off
mhd --config config/runtime.yaml --spec-file 01_counter3_basic.txt --yes --narrative-mode llm --run-name demo_counter_llm
```

## 6. Basic Multimodule Run

```bash
mhd --config config/scenarios/demo_multimodule.yaml --spec-file demo_inv1_wrapper_multimodule.txt --yes --narrative-mode llm --run-name demo_multimodule_buf_llm
```

## 7. Basic Benchmark Run With Ten Problems

```bash
mhd doctor --config config/runtime.benchmark.yaml --benchmark
mhd benchmark list-problems --config config/runtime.benchmark.yaml --max-problems 10
mhd benchmark run --config config/runtime.benchmark.yaml --campaign demo_readiness --run-id smoke10_demo --max-problems 10
```

## 8. Show Run Artifacts

UI actions:

- Open `artifacts/generated/dag.json`
- Open `artifacts/generated/design_context.json`
- Open `artifacts/task_memory/specs/planning_spec.json`
- Open `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo/run_manifest.json`
- Open `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo/canonical/summary.csv`
- Open `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo/canonical/aggregate.json`

## 9. Show AgentOps Prettified Cost Elements

UI actions:

- Open the AgentOps dashboard in the browser
- Filter or search for `demo_counter_det`
- Filter or search for `demo_counter_off`
- Filter or search for `demo_counter_llm`
- Filter or search for `demo_multimodule_buf_llm`
- Filter or search for the benchmark run under `demo_readiness / smoke10_demo`
- Click into a trace and show token and cost breakdowns

Fallback local files:

- `artifacts/observability/cost_summary.json`
- `artifacts/observability/costs.jsonl`

## 10. Show YAML Config Per-Agent LLMs

```bash
sed -n '1,120p' config/domains/agents.yaml
sed -n '1,40p' config/scenarios/wavefix_smoke.yaml
```

## 11. Show RAG Embedded In Runs

```bash
find artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo -name benchmark_prompt.txt | head -n 3
find artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo -name design_context.json | head -n 3
```

UI actions:

- Open one returned `benchmark_prompt.txt`
- Open the nearby `design_context.json`
- Point out that prompt/context is carried into the run artifacts
- Open these source files in the editor:
  - `orchestrator/context_builder.py`
  - `agents/implementation/worker.py`
  - `agents/debug/worker.py`
- Show the `benchmark_prompt`, `library_refs`, and context payload usage

## 12. Spec-Helper Workflow 3-Bit Counter Example

```bash
mhd --config config/runtime.yaml --spec-file "/Users/jacoboforero/Desktop/School/SD1 Proj/artifacts/tmp/demo_bad_counter3_spec.txt" --narrative-mode off --run-name demo_spec_helper
```

UI actions:

- Answer the spec-helper clarification question in plain English
- When it asks `Proceed to execution?`, type `n`
- Stop after the repaired spec/planning handoff

## Risk Notes

- Highest-risk live segments are the multimodule run and the live 10-problem benchmark run
- If timing forces a cut, cut the multimodule segment first
- If stability forces a cut, switch the benchmark segment to `--dry-run` or show precomputed benchmark artifacts instead
