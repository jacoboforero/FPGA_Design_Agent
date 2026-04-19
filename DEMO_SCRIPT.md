# Demo Script

## Background Prep Before The Presentation

Prepare the shell environment before the audience is present. Installed `mhd`
reads credentials from the shell, not from a workspace `.env`.

Set your repo root once so the script commands work from any directory.

On this demo machine:

```bash
export REPO_ROOT="/Users/jacoboforero/Desktop/School/SD1 Proj"
```

If the repo is cloned somewhere else, replace that path with the actual repo root.

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
bash "$REPO_ROOT/scripts/reset_demo_user_config.sh"
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
ls artifacts/rag/memory.json
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
mhd --spec-file 01_counter3_basic.txt --rag off --llm-quasi-deterministic --llm-seed 7 --yes --narrative-mode deterministic --run-name demo_counter_det
```

## 5. Show Different Narrative Modes

```bash
mhd --spec-file 01_counter3_basic.txt --rag off --llm-quasi-deterministic --llm-seed 7 --yes --narrative-mode off --run-name demo_counter_off
mhd --spec-file 01_counter3_basic.txt --rag off --llm-quasi-deterministic --llm-seed 7 --yes --narrative-mode llm --run-name demo_counter_llm
```

## 6. Basic Multimodule Run

```bash
mhd --spec-file demo_inv1_wrapper_multimodule.txt --rag on --llm-quasi-deterministic --llm-seed 7 --yes --narrative-mode llm --run-name demo_multimodule_buf_llm
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
- Open `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo/canonical/aggregate.json`

What to say while showing them:

- `artifacts/generated/dag.json`: this is the planner output that turns the spec into an executable dependency graph, so you can immediately see whether the run is single-module or decomposed into leaf and top-level work.
- `artifacts/generated/dag.json`: for the multimodule example, call out that the top module depends on the leaf module, which is why the system builds and validates the leaf before the wrapper.
- `artifacts/generated/design_context.json`: this is the normalized contract the downstream agents actually consume, with interface, behavior, verification, and acceptance expectations in one machine-readable file.
- `artifacts/generated/design_context.json`: emphasize that this file is what makes the pipeline reproducible, because the later stages are no longer improvising off raw prose alone.
- `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo/canonical/aggregate.json`: this is the structured benchmark rollup, so it is the fastest file to open when you want pass-rate, counts, and high-level outcome without digging through per-problem outputs.
- `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_demo/canonical/aggregate.json`: frame it as the presentation-friendly benchmark artifact, because it condenses the official analyzer outputs into a cleaner JSON summary for inspection.

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
nano "$HOME/.config/mhd/domains/agents.yaml"
nano "$HOME/.config/mhd/runtime.benchmark.yaml"
```

## 11. Spec-Helper Workflow 3-Bit Counter Example

```bash
mhd --spec-file "$HOME/Desktop/mhd-homebrew-demo/demo_bad_counter3_spec.txt" --narrative-mode off --run-name demo_spec_helper
```

UI actions:

- First, when it asks `Select 1/2/3:`, type `1` to show that the spec file can be edited manually.
- Return to the prompt, then type `3` to let the spec helper propose a draft.
- Reject that draft and return to the prompt.
- Finally, type `2` and paste this answer if it asks about the reference model or scoreboard plan:

```text
Use a cycle-accurate reference model that tracks the expected count and rollover on each rising clock edge. The scoreboard should compare the DUT count and rollover outputs against that reference every cycle, including reset behavior, enable hold behavior, and the 7-to-0 wrap with a one-cycle rollover pulse.
```

- When it asks `Proceed to execution?`, type `n`
- Stop after the repaired spec/planning handoff

## Risk Notes

- Highest-risk live segments are the multimodule run and the live 10-problem benchmark run
- If timing forces a cut, cut the multimodule segment first
- If stability forces a cut, switch the benchmark segment to `--dry-run` or show precomputed benchmark artifacts instead
- If you need to show an explicit override, use `mhd --config "$HOME/.config/mhd/runtime.yaml" ...` as the advanced path rather than relying on copied workspace config
