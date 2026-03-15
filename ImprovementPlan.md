# Improvement Plan

## Goal

Raise the VerilogEval benchmark result from 82.05% to a level that is competitive with the strongest published agentic/planning systems. The immediate target is to close the gap to the lightweight GPT-4.1 loop result (~85%) and then push toward the 95% class of results reported on newer VerilogEval-Human variants.

## How This Fits the Current YAML Setup

This repo already has a typed runtime configuration system in `core/runtime/config.py` and uses YAML files such as `config/runtime.yaml` and `config/runtime.testspec_matrix.yaml`. The existing config surface is useful, but it is narrower than the first version of this plan assumed.

What the current YAML system can already control directly:

- `active_preset` and `presets.*` for `spec_profile`, `verification_profile`, `allow_repair_loop`, `interactive_spec_helper`, and `benchmark_mode`
- `workers.pool_sizes.*` for concurrency
- `llm.default_model`, `llm.temperature`, `llm.top_p`
- `llm.agent_overrides` for per-agent model/provider selection
- `llm.rate_control.*` for in-flight throttling and 429 backoff behavior
- `debug.max_retries` and `debug.max_attempts`
- `benchmark.*` for benchmark sampling, oracle paths, sim timeout, and near-miss retry policy
- `tools.*`, `lint.*`, and `sim.*`

What the current YAML system cannot express yet, but this plan needs:

- benchmark flow selection such as `direct_single_module` vs `orchestrated`
- planner gating / planner policy
- raw prompt preservation policy
- benchmark-specific execution-policy flags such as `debug_rtl_only`, `disable_tb_generation`, and `benchmark_use_public_testbench`
- per-agent decoding controls beyond provider/model
- benchmark-specific worker or rate-control presets beyond whole-file overrides

Because of that, the plan below is split into:

1. Immediate work that can be driven by YAML today.
2. Required config/schema extensions so future benchmark options fit the current setup cleanly instead of being hardcoded in the runner.

## Important Benchmark Caveat

The published ~95% planning results are not on the exact same benchmark setup we just ran. They are mostly on VerilogEval-Human v2 / Human 2, not the original 156-problem canonical spec-to-RTL run. That means our first obligation is not to claim equivalence, but to build a system that:

1. Cleanly beats our current 82.05% on the original 156-problem run.
2. Matches or exceeds the lightweight GPT-4.1 repair loop on the same setup.
3. Then extends to the harder/newer benchmark variants.

## Priority 1: Remove Benchmark-Mode Tax

Our current benchmark path adds orchestration overhead without getting real planner benefit.

- Preserve the raw benchmark prompt verbatim for implementation and debug.
- Stop flattening prompt structure into a generic checklist summary when running VerilogEval.
- Add a benchmark-direct mode that bypasses the spec/planner normalization path for clearly single-module problems.
- Keep the current spec/planner flow for real multi-module design tasks, but do not force it into the benchmark path when it adds no value.
- Remove unnecessary benchmark restrictions such as the forced Verilog-2001-only instruction set when the harness already accepts SystemVerilog.
- Fix benchmark interface canonicalization so equivalent declarations like `[3:1]` and `[2:0]` are not treated as mismatches.

How this maps to the current setup:

- `legacy-lightweight` already exists in the VerilogEval runner and is the closest thing to a direct baseline today.
- The missing piece is configurability: the runner currently hardcodes benchmark `execution_policy` values in `apps/cli/run_verilog_eval.py` instead of loading them from YAML.
- We should add a `benchmark.execution_policy` block or a dedicated `benchmark_runner` block to the config schema so benchmark flow options live in YAML rather than inside the CLI implementation.
- Proposed new config keys:
  - `benchmark.flow_mode: orchestrated | legacy_lightweight | direct_single_module`
  - `benchmark.prompt_mode: normalized | raw_verilog_eval`
  - `benchmark.debug_rtl_only: true|false`
  - `benchmark.disable_tb_generation: true|false`
  - `benchmark.use_public_testbench: true|false`
  - `benchmark.interface_equivalence: strict | canonical_width`

## Priority 2: Fix the Planner Agent Strategy

The planner is not currently weak in the sense of “bad graph search”; it is mostly inactive on VerilogEval because every benchmark case is being reduced to a single-node DAG.

- Make planner activation selective.
- Add a planner gate:
  - `direct_single_module` for standard VerilogEval prompts.
  - `planned_multi_module` only when the prompt or spec actually implies decomposition.
- Teach the planner to preserve benchmark semantics rather than rephrasing them into generic contracts.
- Add decomposition heuristics for cases where planning really should help:
  - explicit multi-module prompts
  - complex FSM + datapath separation
  - reusable counters/decoders/arbiters
  - designs with natural sub-block boundaries
- Evaluate planner quality explicitly with new metrics:
  - multi-node DAG rate
  - decomposition correctness
  - integration success rate
  - pass rate delta versus direct mode
- Do not treat “graph-based planning exists” as success. The planner must demonstrate measured benefit over a direct loop.

How this maps to the current setup:

- Today, presets only choose `spec_profile` and `verification_profile`; they do not control planner behavior.
- We should extend the config schema with explicit planner controls instead of overloading `spec_profile`.
- Proposed new config block:
  - `benchmark.planner.enabled: true|false`
  - `benchmark.planner.policy: always | never | auto_single_module_bypass | auto_decompose`
  - `benchmark.planner.decomposition_heuristics: [...]`
- This lets us run planner ablations cleanly with `--config` rather than patching code between experiments.

## Priority 3: Strengthen the Repair Loop

The lightweight paper loop is winning partly because it gets more refinement opportunities with less overhead.

- Increase benchmark repair depth from 2 retries to a range closer to 8-10 iterations.
- Keep the current near-miss bonus, but do not rely on it as the main mechanism.
- Add candidate branching:
  - multiple initial implementations
  - multiple repair candidates on hard failures
  - judge/rank/select before the next simulation
- Add repeated-failure detection that changes strategy aggressively instead of making small local edits.
- Record and compare failure signatures so the system avoids recycling the same incorrect patch idea.

How this maps to the current setup:

- `debug.max_retries` and `debug.max_attempts` already exist in YAML and should be used immediately for benchmark experiments.
- `benchmark.near_miss_*` already exists and can stay, but it should become a secondary mechanism rather than the main way we get more search depth.
- Candidate branching is not config-expressible yet. To support it cleanly, add a benchmark repair block:
  - `benchmark.repair.max_debug_retries`
  - `benchmark.repair.max_llm_attempts_per_debug`
  - `benchmark.repair.initial_candidates`
  - `benchmark.repair.debug_candidates`
  - `benchmark.repair.stagnation_strategy: patch | rewrite | branch`
- The runner should prefer these benchmark-specific values over the global `debug.*` defaults when `preset=benchmark`.

## Priority 4: Improve Failure Localization and Debug Signal

Our current distillation is too generic for hard FSM/control problems.

- Add cycle-accurate failure anchoring whenever possible.
- Capture and compare DUT state progression around first mismatch.
- Produce structured signal deltas instead of mostly free-form log excerpts.
- Add checkpoint-style traces for FSM/stateful problems.
- Add stronger waveform summarization:
  - relevant signals only
  - first mismatch window
  - state/output/input correlation
- Add benchmark-specific failure analyzers for common classes:
  - FSM off-by-one
  - counter enable timing
  - reset sequencing
  - pulse-width / one-cycle-late bugs

How this maps to the current setup:

- The existing `sim.*` block already controls VCD extraction windows and limits, so some of this work can start without schema changes.
- We should first tune:
  - `sim.fail_window_before`
  - `sim.fail_window_after`
  - `sim.vcd_max_signals`
  - `sim.vcd_max_changes_per_signal`
  - `sim.vcd_time_window_before`
  - `sim.vcd_time_window_after`
- If we add richer benchmark-specific distillation behavior, it should live under a new block rather than overloading generic `sim.*`:
  - `benchmark.distill.require_cycle_anchor`
  - `benchmark.distill.fsm_focus`
  - `benchmark.distill.checkpoint_trace`

## Priority 5: Remove Orchestration Reliability Losses

Some of our misses are not model-quality misses.

- Fix retry routing permanently so retryable tasks always go to the correct worker queue.
- Lower or serialize benchmark-time LLM concurrency to avoid TPM rate-limit failures.
- Add benchmark-safe backoff/retry handling for 429s without burning repair opportunities.
- Ensure every failed attempt snapshots complete task-memory artifacts for postmortem analysis.
- Treat timeout / infrastructure / protocol failures as separate reliability regressions and drive them to zero.

How this maps to the current setup:

- This is the area best supported by current YAML.
- Immediate changes can be tested via:
  - `workers.pool_sizes.*`
  - `llm.rate_control.max_in_flight_min/default/max`
  - `llm.rate_control.backoff_on_429`
  - `broker.task_max_retries`
  - `benchmark.sim_run_timeout_s`
- For benchmark runs, we should create low-concurrency configs that intentionally reduce throughput in exchange for stability.

## Priority 6: Add an Apples-to-Apples Evaluation Matrix

We need proof about what helps.

- Baseline A: raw GPT-4.1 single-shot.
- Baseline B: raw GPT-4.1 + lightweight repair loop.
- System C: current orchestrator without planner normalization.
- System D: selective planner + improved repair loop.
- System E: full planner/orchestrator on genuinely decomposable tasks.

For each configuration, measure:

- pass rate
- tokens per solved problem
- wall-clock time
- failure taxonomy
- infrastructure failure count
- hard-problem recovery rate

How this maps to the current setup:

- This repo already supports experiment separation naturally through `--config` and `--preset`.
- We should stop treating `config/runtime.yaml` as the only benchmark config and instead create dedicated experiment files so every benchmark run is reproducible from YAML alone.
- Recommended config files:
  - `config/runtime.verilog_eval_baseline.yaml`
  - `config/runtime.verilog_eval_lightloop.yaml`
  - `config/runtime.verilog_eval_orchestrated.yaml`
  - `config/runtime.verilog_eval_orchestrated_low_concurrency.yaml`
  - `config/runtime.verilog_eval_planner_ablation.yaml`
- The benchmark manifest already records the config path, so this fits the current artifact model directly.

## Immediate YAML-Only Actions

These changes fit the current config system without adding new schema fields:

1. Create a benchmark config variant that reduces `workers.pool_sizes.reflection`, `workers.pool_sizes.debug`, and `workers.pool_sizes.simulation` to 1 for stability.
2. Tighten `llm.rate_control.max_in_flight_default` and `llm.rate_control.max_in_flight_max` to reduce 429 losses during benchmark runs.
3. Raise `debug.max_retries` from 2 to a higher benchmark value in a dedicated config file.
4. Raise `debug.max_attempts` if local JSON/protocol failures remain a problem.
5. Tune `benchmark.sim_run_timeout_s` and `sim.*` windows for better distillation on hard cases.
6. Use `llm.agent_overrides` to test stronger models selectively for `debug`, `reflection`, or `implementation` if desired.
7. Use dedicated config files plus `--config` rather than manually editing the default runtime file between runs.

## Required Config / Schema Extensions

These changes are needed so the plan fits the repo cleanly instead of depending on code-local hardcoded flags:

1. Extend `BenchmarkConfig` with benchmark execution-policy fields so `run_verilog_eval.py` stops hardcoding them.
2. Extend `PresetConfig` or add a dedicated benchmark runner block for planner flow selection.
3. Extend `LlmAgentOverrideConfig` beyond provider/model so we can tune per-agent `temperature`, `top_p`, `max_tokens`, and maybe `request_timeout_s` from YAML.
4. Add benchmark-specific planner and repair sub-blocks rather than trying to encode them through generic `spec_profile` and `debug.*`.
5. Update the benchmark runner to build `execution_policy` from config instead of writing it inline.

## Proposed Experiment Structure In This Repo

Short term, the repo should support benchmark experiments like this:

1. `python apps/cli/run_verilog_eval.py run --config config/runtime.verilog_eval_baseline.yaml --preset benchmark ...`
2. `python apps/cli/run_verilog_eval.py run --config config/runtime.verilog_eval_lightloop.yaml --preset benchmark --legacy-lightweight ...`
3. `python apps/cli/run_verilog_eval.py run --config config/runtime.verilog_eval_orchestrated_low_concurrency.yaml --preset benchmark ...`
4. `python apps/cli/run_verilog_eval.py run --config config/runtime.verilog_eval_planner_ablation.yaml --preset benchmark ...`

That keeps all benchmark variants aligned with the way this codebase already records `config_path`, `preset`, run metadata, and artifacts.

## Success Criteria

- Zero orchestration/pathology failures on the first 20 benchmark problems.
- Zero rate-limit-induced benchmark losses.
- Zero harness-only interface mismatch losses.
- At least match the lightweight GPT-4.1 loop on the original 156-problem run.
- Reach 90%+ on the original canonical run before claiming planner value.
- Then push toward 95% on the newer VerilogEval-Human benchmark family with stronger decomposition and debug infrastructure.

## Recommended Order of Execution

1. Fix benchmark-mode prompt preservation, interface checking, routing, and rate-limit handling.
2. Add dedicated benchmark config files for baseline, lightweight loop, orchestrated low-concurrency, and planner ablation runs.
3. Move benchmark execution-policy flags out of `run_verilog_eval.py` and into typed YAML-backed config.
4. Add the direct raw-prompt benchmark baseline with 8-10 repair iterations.
5. Compare direct mode versus current orchestrator on the same 156 problems.
6. Upgrade distillation/debug quality until repair consistently helps on hard FSM/control tasks.
7. Reintroduce planner value selectively and prove it on workloads where decomposition is actually present.
