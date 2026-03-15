# Improvement Plan

## Goal

Raise the VerilogEval benchmark result from 82.05% to a level that is competitive with the strongest published agentic/planning systems. The immediate target is to close the gap to the lightweight GPT-4.1 loop result (~85%) and then push toward the 95% class of results reported on newer VerilogEval-Human variants.

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

## Priority 5: Remove Orchestration Reliability Losses

Some of our misses are not model-quality misses.

- Fix retry routing permanently so retryable tasks always go to the correct worker queue.
- Lower or serialize benchmark-time LLM concurrency to avoid TPM rate-limit failures.
- Add benchmark-safe backoff/retry handling for 429s without burning repair opportunities.
- Ensure every failed attempt snapshots complete task-memory artifacts for postmortem analysis.
- Treat timeout / infrastructure / protocol failures as separate reliability regressions and drive them to zero.

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

## Success Criteria

- Zero orchestration/pathology failures on the first 20 benchmark problems.
- Zero rate-limit-induced benchmark losses.
- Zero harness-only interface mismatch losses.
- At least match the lightweight GPT-4.1 loop on the original 156-problem run.
- Reach 90%+ on the original canonical run before claiming planner value.
- Then push toward 95% on the newer VerilogEval-Human benchmark family with stronger decomposition and debug infrastructure.

## Recommended Order of Execution

1. Fix benchmark-mode prompt preservation, interface checking, routing, and rate-limit handling.
2. Add the direct raw-prompt benchmark baseline with 8-10 repair iterations.
3. Compare direct mode versus current orchestrator on the same 156 problems.
4. Upgrade distillation/debug quality until repair consistently helps on hard FSM/control tasks.
5. Reintroduce planner value selectively and prove it on workloads where decomposition is actually present.
