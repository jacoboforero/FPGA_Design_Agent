# Demo Script

## Background Prep Before The Presentation

Prepare the shell environment before the audience is present. Installed `mhd`
reads credentials from the shell, not from a workspace `.env`.

Set your clone path once so the script commands work from any directory:

```bash
export REPO_ROOT="/absolute/path/to/your/cloned/FPGA_Design_Agent"
```

Sync the real demo values from the repo `.env` into `~/.zshrc`:

```bash
bash "$REPO_ROOT/scripts/sync_demo_shell_env.sh"
exec zsh -l
```

That helper updates these entries in place without printing secret values:

- `OPENAI_API_KEY`
- `AGENTOPS_API_KEY`
- `RABBITMQ_URL`

Verify the shell state:

```bash
printenv OPENAI_API_KEY | sed 's/./*/g'
printenv AGENTOPS_API_KEY | sed 's/./*/g'
echo "$RABBITMQ_URL"
```

Optional cleanup and environment prep:

```bash
brew uninstall --ignore-dependencies --force mhd || true
brew untap local/mhd-demo || true
brew services start rabbitmq
```

## Live Presentation Starts Here

## 1. Homebrew Install

Run from any directory:

```bash
bash "$REPO_ROOT/scripts/test_homebrew_install.sh"
```

## 2. Prepare Clean Demo Workspace

```bash
bash "$REPO_ROOT/scripts/setup_homebrew_demo_env.sh"
cd "$HOME/Desktop/mhd-homebrew-demo"
```

## 3. Show Standard Shell Setup

Explain:

- `mhd` reads credentials from the shell environment
- first run seeds config into `~/.config/mhd` or `$XDG_CONFIG_HOME/mhd`
- the workspace is just a normal user directory with spec files and generated artifacts
- OpenAI-backed RAG is already part of the normal engineer flow and shows up through the narration, not as a separate mode
- this workspace is pre-seeded with one curated `buf1_leaf` memory example for the multimodule run only

Verification commands:

```bash
mhd --help
mhd benchmark --help
mhd doctor
```

## 4. Basic 3-Bit Counter Run

```bash
mhd --spec-file 01_counter3_basic.txt --rag off --llm-deterministic --llm-seed 7 --yes --narrative-mode deterministic --run-name demo_counter_det
```

## 5. Show Different Narrative Modes

```bash
mhd --spec-file 01_counter3_basic.txt --rag off --llm-deterministic --llm-seed 7 --yes --narrative-mode off --run-name demo_counter_off
mhd --spec-file 01_counter3_basic.txt --rag off --llm-deterministic --llm-seed 7 --yes --narrative-mode llm --run-name demo_counter_llm
```

## 6. Basic Multimodule Run

```bash
mhd --spec-file demo_inv1_wrapper_multimodule.txt --rag on --llm-deterministic --llm-seed 7 --yes --narrative-mode llm --run-name demo_multimodule_buf_llm
```

Point out during the run:

- the narration should naturally mention when it consulted prior designs
- the leaf module is the curated retrieval target in this demo workspace

## 7. Basic Benchmark Run With Ten Problems

```bash
mhd doctor --benchmark
mhd benchmark list-problems --max-problems 10
mhd benchmark run --campaign demo_readiness --run-id smoke10_demo --max-problems 10
```

Point out during the run:

- this benchmark path intentionally runs with RAG disabled by default
- it uses the Verilog-Eval public reference assets, not generated testbenches

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
sed -n '1,120p' "$HOME/.config/mhd/domains/agents.yaml"
sed -n '1,40p' "$HOME/.config/mhd/runtime.benchmark.yaml"
```

## 11. Spec-Helper Workflow 3-Bit Counter Example

```bash
mhd --spec-file demo_bad_counter3_spec.txt --narrative-mode off --run-name demo_spec_helper
```

UI actions:

- Answer the spec-helper clarification question in plain English
- When it asks `Proceed to execution?`, type `n`
- Stop after the repaired spec/planning handoff

## Risk Notes

- Highest-risk live segments are the multimodule run and the live 10-problem benchmark run
- If timing forces a cut, cut the multimodule segment first
- If stability forces a cut, switch the benchmark segment to `--dry-run` or show precomputed benchmark artifacts instead
- If you need to show an explicit override, use `mhd --config "$HOME/.config/mhd/runtime.yaml" ...` as the advanced path rather than relying on copied workspace config
