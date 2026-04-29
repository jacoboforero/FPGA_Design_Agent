# VerilogEval-v2 Optimization Log - 2026-04-29

## Goal

Improve VerilogEval-v2 benchmark performance on the hard subset that failed in the GPT-4o full run, using generalizable prompt or architecture changes only.

## Constraints

- Do not add benchmark-problem-specific logic or prompt text.
- Iterate primarily with GPT-4.1.
- If spend threatens the budget, use GPT-4.1-mini or GPT-4o-mini for exploratory runs and confirm promising changes with GPT-4.1.
- Keep iterative optimization spend within the user-approved $20 budget; track later full-set confirmation runs separately when explicitly requested.
- Preserve the current planning-first pipeline shape unless evidence from failures justifies a targeted change.

## Baseline Context

- GPT-4.1 smoke run on first 10 canonical VerilogEval-v2 problems: 10/10 pass, estimated cost about $0.015.
- GPT-4o full canonical run: 117/156 pass, 75.00%, estimated cost about $6.03.
- GPT-4o failed subset:
  `Prob034, Prob057, Prob062, Prob066, Prob070, Prob082, Prob086, Prob089, Prob091, Prob093, Prob094, Prob099, Prob104, Prob112, Prob113, Prob116, Prob117, Prob120, Prob121, Prob122, Prob124, Prob125, Prob133, Prob136, Prob137, Prob139, Prob140, Prob141, Prob144, Prob145, Prob146, Prob147, Prob149, Prob150, Prob151, Prob153, Prob154, Prob155, Prob156`.

## Result Summary

Local rows use the official VerilogEval analyzer output. Scope matters: the old GPT-4.1 baseline was only run on the 39-problem hard subset from the GPT-4o full run, while the final GPT-4.1 run was a full 156-problem canonical run.

| Run | Scope | Model / config | System state | Result | Pass rate | Cost | Artifact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gpt4o_full156` | Full 156 | GPT-4o, `config/runtime.benchmark.gpt4o.local.yaml` | Earlier full-run baseline | 117/156 | 75.00% | $6.03 | `artifacts/benchmarks/verilog_eval/frontier_compare_20260429/gpt4o_full156/canonical/summary.txt` |
| `gpt41_baseline_fail39` | 39 GPT-4o failures | GPT-4.1, `config/runtime.benchmark.yaml` | Old GPT-4.1 hard-subset baseline | 14/39 | 35.90% | $3.39 | `artifacts/benchmarks/verilog_eval/hard_subset_iter_20260429/gpt41_baseline_fail39/canonical/summary.txt` |
| `gpt41_repair3_v5_fail39_confirm` | 39 GPT-4o failures | GPT-4.1, `config/runtime.benchmark.repair3.yaml` | Mid-optimization hard-subset confirmation | 19/39 | 48.72% | $5.41 | `artifacts/benchmarks/verilog_eval/hard_subset_iter_20260429/gpt41_repair3_v5_fail39_confirm/canonical/summary.txt` |
| `gpt41_final_v11_full156_current` | Full 156 | GPT-4.1, `config/runtime.benchmark.repair3.yaml` | Final general repair/prompt changes | 137/156 | 87.82% | $8.26 | `artifacts/benchmarks/verilog_eval/full156_final_20260429/gpt41_final_v11_full156_current/canonical/summary.txt` |

Comparison against the old GPT-4.1 hard-subset result:

- On the original 39 GPT-4o failures, the final full GPT-4.1 run passed 21/39, up from 14/39 in `gpt41_baseline_fail39`.
- That is a net +7 solved cases on the same hard subset. It recovered `Prob034, Prob057, Prob062, Prob066, Prob125, Prob133, Prob154, Prob155` and regressed `Prob086`.
- Against the GPT-4o full run, the final GPT-4.1 run solved 21 of the 39 GPT-4o failures but newly failed `Prob152`, for a net full-set gain of +20 solved cases and +12.82 percentage points.

## External Context

These comparisons are directional, not apples-to-apples. Published numbers vary by prompt policy, sample count, model version, retry budget, testbench access, and whether the system is one-shot, single-agent, or multi-agent.

| Source | Reported setup | Reported result | How this run compares |
| --- | --- | --- | --- |
| Pinckney et al., "Revisiting VerilogEval" ([arXiv:2408.11053](https://arxiv.org/abs/2408.11053)) | GPT-4o on VerilogEval spec-to-RTL | About 63% pass rate | Our GPT-4o full run is 75.00%, likely reflecting the local EDA-feedback loop and prompt/runtime differences rather than raw GPT-4o alone. |
| "Survey and Benchmarking of Large Language Models for RTL Code Generation" ([preprint](https://www.preprints.org/manuscript/202509.1681)) | GPT-4.1 baseline and lightweight agentic refinement on VerilogEval | 75.00% baseline, 85.26% agentic | Our final GPT-4.1 full run is 87.82%, slightly above that reported GPT-4.1 agentic result, but with a different repair loop and canonical sampling policy. |
| ChipAgents DVCon slides ([PDF](https://dvcon-proceedings.org/wp-content/uploads/5014-Accelerating-Design-Verification-with-AI-Agents.pdf)) | Agentic VerilogEval-v2 systems | ChipAgents 97.4% (152/156), MAGE 95.5% (149/156), VerilogCoder 94.2% (147/156) | Our 87.82% remains below reported top agentic systems, but is materially above single-shot/model-only GPT-4o/GPT-4.1 reference points. |
| MAGE paper ([PDF](https://stable-lab.github.io/MAGE/static/paper/Multi_Agent_LLM4RTL.pdf)) | Multi-agent RTL generation with candidate sampling and debug feedback | 95.7% on VerilogEval-Human v2 | The gap suggests the next gains likely require stronger candidate selection, state-checkpoint feedback, or domain-specific repair strategy, not just broader retry depth. |

## Research Threads

- Multi-agent RTL generation papers emphasize structured verification feedback, root-cause reflection, module-interface preservation, and escalation only after evidence accumulates.
- Candidate systems to map against failures: MAGE, VerilogCoder, VFlow, EstCoder, ACE-RTL, ChipCraftBrain, PEFA-AI, VeriMoA, and HDLFORGE.
- Current working hypothesis: the largest gains will come from better failure distillation and repair discipline, not from one-shot generation changes.

## Running Experiments

### `gpt41_baseline_fail39`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.yaml`
- Scope: the 39 problems that failed under GPT-4o.
- Result: 14/39 pass, 25/39 fail.
- Estimated cost: about $3.39.
- Passing problems:
  `Prob086, Prob089, Prob091, Prob094, Prob104, Prob112, Prob117, Prob120, Prob121, Prob122, Prob137, Prob150, Prob151, Prob153`.
- Remaining failures:
  `Prob034, Prob057, Prob062, Prob066, Prob070, Prob082, Prob093, Prob099, Prob113, Prob116, Prob124, Prob125, Prob133, Prob136, Prob139, Prob140, Prob141, Prob144, Prob145, Prob146, Prob147, Prob149, Prob154, Prob155, Prob156`.
- Purpose: establish which GPT-4o failures are still hard for GPT-4.1 before making changes.

### `gpt41_evidence_v1_diag8`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.yaml`
- Scope: diagnostic slice of 8 baseline failures:
  `Prob034, Prob057, Prob062, Prob066, Prob093, Prob113, Prob116, Prob125`.
- Result: 3/8 pass, 5/8 fail.
- Estimated cost: about $0.86.
- Recovered relative to baseline: `Prob034, Prob057, Prob062`.
- Interpretation: structured `*_ref`/`*_dut` waveform evidence plus stricter RTL-only debug guidance fixes early-X/race misclassification and at least one direct truth-table/K-map repair class. It does not fully solve harder K-map don't-care/minimization failures or sequential timing/FSM failures.

### `gpt41_counterexamples_v2_diag5`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.yaml`
- Scope: the five failures from `gpt41_evidence_v1_diag8`:
  `Prob066, Prob093, Prob113, Prob116, Prob125`.
- Change under test: include compact counterexample history in the debug prompt, not just the current distilled failure.
- Result: 1/5 pass, 4/5 fail.
- Estimated cost: about $0.70.
- Recovered relative to prior diagnostic: `Prob113`.
- Interpretation: accumulated counterexamples help a K-map case that previously regressed into illegal array indexing, but the remaining cases need stronger strategy selection or more direct combinational/FSM reasoning.

### `gpt41_bitdiff_v3_diag2`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.yaml`
- Scope: `Prob066, Prob093`.
- Change under test: add deterministic `differing_bit_indices` to vector reference/DUT pairs and instruct debug to use those Verilog bit indices.
- Result: 0/2 pass.
- Estimated cost: about $0.26.
- Interpretation: bit-index disambiguation alone does not fix these two. Keep the metadata because it is correct and useful, but the next gains likely need stronger repair strategy rather than clearer bit labels alone.

### `gpt41_kmapcase_v4_diag3`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.yaml`
- Scope: `Prob093, Prob116, Prob125`.
- Change under test: bias combinational/K-map generation and debug toward exact header-order mapping and complete `case`/`casez` tables.
- Result: 0/3 pass.
- Estimated cost: about $0.38.
- Interpretation: this guidance did not recover the remaining hard K-map cases. Keep the guidance because it is generally safer, but it is not enough without better extraction/strategy.

### `gpt41_repair3_v5_diag4`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.repair3.yaml`
- Scope: `Prob066, Prob093, Prob116, Prob125`.
- Change under test: allow up to 3 benchmark debug repairs.
- Result: 1/4 pass.
- Estimated cost: about $0.67.
- Recovered: `Prob125`.
- Interpretation: extra repair depth has selective value. It increases average tokens, so use it for the final hard-subset run only if the projected spend remains inside budget.

### `gpt41_repair3_v5_fail25`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.repair3.yaml`
- Scope: the 25 failures from `gpt41_baseline_fail39`.
- Result: 8/25 pass, 17/25 fail.
- Estimated cost: about $4.36.
- Passing problems:
  `Prob034, Prob057, Prob062, Prob113, Prob133, Prob140, Prob146, Prob154`.
- Interpretation: current changes recover 8 of the 25 baseline failures in one broader run. Combined with the 14 baseline passes from the original 39-problem hard subset, this implies 22/39 if those 14 remain stable. A clean 39-problem confirmation run is still needed.

### `gpt41_repair3_v5_fail39_confirm`

- Campaign: `hard_subset_iter_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.repair3.yaml`
- Scope: all 39 GPT-4o failures.
- Result: 19/39 pass, 20/39 fail.
- Estimated cost: about $5.41.
- Passing problems:
  `Prob034, Prob057, Prob062, Prob094, Prob104, Prob112, Prob117, Prob120, Prob121, Prob122, Prob133, Prob137, Prob139, Prob140, Prob146, Prob150, Prob151, Prob153, Prob154`.
- Interpretation: broader confirmation improves raw hard-subset pass count from 14/39 to 19/39, but it regresses several baseline-pass cases. This is a useful research result, not a stable final benchmark claim.

### `gpt41_history_v6_diag7`

- Scope: `Prob066, Prob086, Prob089, Prob091, Prob093, Prob113, Prob125`.
- Change under test: put compact paired reference/DUT history before bulky waveform data, and include that history in counterexample prompts.
- Result: 4/7 pass.
- Estimated cost: about $0.95.
- Passing problems: `Prob086, Prob091, Prob113, Prob125`.
- Interpretation: compact sequence history restores several regressed or unstable repairs, especially sequential/vector cases, but `Prob066`, `Prob089`, and `Prob093` still need stronger evidence or validation.

### `gpt41_context_v7_diag3`

- Scope: `Prob066, Prob089, Prob093`.
- Change under test: add context signal histories and width-normalized values to reference/DUT pairs.
- Result: 0/3 pass.
- Estimated cost: about $0.60.
- Interpretation: context histories alone were too indirect. The model needed rows that align inputs and ref/DUT outputs at the same sampled time.

### `gpt41_iosamples_v8_diag3`

- Scope: `Prob066, Prob089, Prob093`.
- Change under test: add compact observed I/O rows (`io_samples_around_failure`) to each reference/DUT pair.
- Result: 1/3 pass.
- Estimated cost: about $0.41.
- Recovered: `Prob066`.
- Interpretation: observed I/O rows fixed the reset-release edge-capture case without problem-specific logic. `Prob089` still needed better local validation; `Prob093` remains a hard K-map/mux mapping case.

### `gpt41_iosamples_v8_recover8`

- Scope: `Prob034, Prob057, Prob062, Prob066, Prob086, Prob091, Prob113, Prob125`.
- Result: 6/8 pass.
- Estimated cost: about $0.78.
- Passing problems: `Prob034, Prob057, Prob062, Prob066, Prob091, Prob125`.
- Failing problems: `Prob086, Prob113`.
- Interpretation: the recovery set is meaningfully better than baseline, but individual debug repairs remain unstable on some sequential/combinational cases.

### `gpt41_icarus_v9_prob089`

- Scope: `Prob089`.
- Change under test: add local Icarus RTL validation for RTL-only debug patches so SystemVerilog constructs that Verilator accepts but Icarus rejects are caught before the next simulation attempt.
- Result: 1/1 pass.
- Estimated cost: about $0.20.
- Interpretation: the Icarus validation gap was real. This is a general architecture improvement because VerilogEval scoring uses Icarus.

### `gpt41_detdebug_v10_unstable2`

- Scope: `Prob086, Prob113`.
- Change under test: apply canonical benchmark temperature/top_p to debug and reflection agents, not only implementation, for reproducible canonical runs.
- Result: 1/2 pass.
- Estimated cost: about $0.28.
- Passing problem: `Prob113`.
- Failing problem: `Prob086`.
- Interpretation: deterministic debug helps one unstable case but does not solve the LFSR repair failure.

### `gpt41_final_v11_full156_current`

- Campaign: `full156_final_20260429`
- Model: GPT-4.1 via `config/runtime.benchmark.repair3.yaml`
- Scope: full 156-problem canonical VerilogEval-v2 run.
- Result: 137/156 pass, 19/156 fail, 87.82% pass rate.
- Estimated cost: $8.26.
- Total tokens: 3,412,897.
- Failing problems:
  `Prob070, Prob082, Prob086, Prob093, Prob099, Prob113, Prob116, Prob124, Prob136, Prob139, Prob140, Prob141, Prob144, Prob145, Prob146, Prob147, Prob149, Prob152, Prob156`.
- Interpretation: the final full-set run confirms that the general repair/prompt changes moved the system well above the earlier GPT-4o full baseline and the old GPT-4.1 hard-subset baseline. The remaining failures cluster heavily in the late sequential/FSM/counter/LFSR-style problems, with `Prob124` also showing that cellular-automata/K-map style repairs still need more robust strategy selection.

## Changes That Improved The Score

- Structured failure evidence: `workers/distill/worker.py` now emits paired `reference_dut_pairs`, top-level interface signal histories, width-normalized values, compact sample histories, and observed I/O rows around failures.
- Better waveform targeting: VerilogEval mismatch hints now expand to `*_ref`/`*_dut` probes where available, so the debug agent sees the oracle and DUT values side by side.
- Repair discipline: debug prompts now preserve prior counterexamples, require material RTL-only patches, include observed I/O constraints, and give general guidance for reset edge-capture, bit-index interpretation, small truth tables, K-map/header-order mapping, and Icarus-friendly FSM code.
- Runtime validation: debug patches now run local Icarus-oriented RTL validation before the next benchmark simulation attempt.
- Reproducibility: canonical benchmark temperature/top-p settings now apply to implementation, reflection, and debug agents.
- Retry policy: `config/runtime.benchmark.repair3.yaml` allows deeper benchmark debug repair while keeping the same direct single-module benchmark flow.
- Constraint maintained: no problem-specific prompt text or benchmark-problem-specific code paths were added.

## Spend Summary

- Total optimization spend tracked across pre-final GPT-4.1 iteration runs: about $19.25.
- Final full-set GPT-4.1 confirmation run: $8.26.
- Total tracked spend for this benchmark push: about $27.51.
- The final full-set run was requested after the original optimization loop and is tracked separately from the initial $20 iteration budget.

## Decision Log

- Created branch `codex/sable-bench-lattice` for benchmark optimization work.
- Added this log to keep continuity across a long-running optimization session.
- Implemented structured VerilogEval waveform evidence extraction:
  - output mismatch hints now expand to `*_ref` and `*_dut` VCD probes;
  - top-level interface signals are included as waveform hints;
  - distilled datasets now include `reference_dut_pairs`.
- Tightened RTL-only benchmark debug guidance so the debug agent must produce a material RTL patch instead of recommending oracle testbench edits.
- Added compact prior/current counterexample history to debug prompts so repeated failures preserve their input/ref/dut constraints across attempts.
- Added deterministic differing-bit indices for vector reference/DUT pairs.
- Added K-map/truth-table guidance to prefer exact header-order mapping and explicit tables for small combinational functions.
- Added compact paired sample history, context signal history, and observed I/O sample rows to distilled VerilogEval mismatch evidence.
- Added Icarus RTL validation to debug local checks so benchmark compile failures are caught during debug patch validation.
- Made canonical benchmark sampling settings apply to debug and reflection agents, improving reproducibility of benchmark runs.
- Validated the distillation change with `PYTHONPATH=. python3 -m pytest tests/workers/test_distill_worker.py -q`.
