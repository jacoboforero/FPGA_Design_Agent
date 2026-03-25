# Demo Readiness

## Purpose

This document evaluates how ready the current system is for a capstone demo in roughly one week, based on the demo sequence currently under consideration:

1. show a 3-bit counter with a filled spec through the CLI
2. show a simple multi-module design through the CLI that passes
3. show a 3-bit counter with a bad spec to demonstrate the spec helper agent
4. show a benchmark run with a limited problem set
5. show AgentOps plus cost visibility for the runs above

This is not a refactor plan. It is a readiness assessment for what is realistic to demo with the current codebase.

## Overall Assessment

The proposed demo is good. It tells a coherent story:

- happy-path engineering flow
- multi-module capability
- recovery/helpful interaction through spec helper
- benchmark/evaluation capability
- observability and cost accounting

The main issue is not that the story is wrong. The issue is that it is slightly too broad to treat as one long fully live demo with no safety rails. The system is demoable, but some parts are much safer than others.

My current overall assessment is:

- single-module CLI pass: `High`
- multi-module CLI pass: `Low`
- bad-spec spec-helper showcase: `Medium-High`
- tiny benchmark run: `High`
- local cost/observability summary: `High`
- hosted AgentOps dashboard as a live dependency: `Medium`

The best version of this demo is:

- keep the live engineer examples very small
- keep the benchmark scope extremely small
- treat local observability artifacts as primary
- treat hosted AgentOps as a bonus, not the only way to show costs

## Latest Retest On 2026-03-23

This section reflects a fresh live retest on the current `homebrew-cli-demo` branch state, using the actual CLI workflow in the app container.

Validated positive results:

- `PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml --spec-file tests/test_specs/01_counter3_basic.txt --yes --narrative-mode off --run-name demo_retest_counter3_basic_20260323`
  Result: `PASS` on the first try.
  Notes: this is now the safest current live CLI example. It reached `sim_attempt1: SUCCESS` and `acceptance_attempt1: SUCCESS`. Observability summary: `artifacts/observability/demo_retest_counter3_basic_20260323_summary.json`.

- interactive bad-spec helper rehearsal using `artifacts/tmp/demo_bad_counter3_spec.txt`
  Result: the helper behavior itself worked.
  Notes: the helper asked a single plain-English clarification question about the missing reference-checking plan, accepted a chat answer, and resumed planning/execution automatically. It did not expose internal `L*` jargon in the interaction. The downstream run still failed later in `tb_lint`/`debug`, so this is good as a helper demo, not as a second live end-to-end success path. Observability summary: `artifacts/observability/demo_retest_bad_counter3_helper_pty_20260323_summary.json`.

- `PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign demo_readiness --run-id smoke10_20260323_retest2 --max-problems 10`
  Result: `PASS` with `10/10`.
  Notes: benchmark artifacts were generated successfully under `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_20260323_retest2/`, including `run_manifest.json`, `canonical/summary.txt`, `canonical/summary.csv`, and `canonical/aggregate.json`.

Negative results that materially affect the demo:

- `tests/test_specs/02_counter3_load.txt`
  Result: `FAIL`.
  Notes: it failed in `tb_lint_attempt1`, then `debug_attempt1`, and is not demo-safe.

- `tests/test_specs/demo_and2_structured.txt`
  Result: `PASS`, but only after retries.
  Notes: it required repeated TB/debug repair and only passed on `sim_attempt3`. This is now a fallback, not the preferred live example.

- `tests/test_specs/demo_inv1_wrapper_multimodule.txt`
  Result: `FAIL`.
  Notes: `inv1_leaf` passed, but `inv1_top` failed after repeated top-level `tb_lint`/`sim`/`debug` churn through attempt 4. Observability summary: `artifacts/observability/demo_retest_inv1_wrapper_multimodule_20260323_summary.json`.

- `tests/test_specs/demo_and_not_multimodule.txt`
  Result: `FAIL`.
  Notes: `inv1_cell` passed, but `and2_cell` failed at `tb_lint_attempt1`, then `debug_attempt1`, causing the top-level run to fail. Observability summary: `artifacts/observability/demo_retest_and_not_multimodule_20260323_summary.json`.

- `tests/test_specs/05_pwm_led_multimodule.txt`
  Result: `FAIL` during spec collection.
  Notes: current error is `Spec/module mismatch between Module blocks and L4.block_diagram non-standard nodes; missing Module section(s): pwm_counter8, duty_reg8, pwm_compare8.`

Current bottom line from the retest:

- the live single-module CLI demo is ready if you use `tests/test_specs/01_counter3_basic.txt`
- the spec-helper interaction is ready to show as an interaction
- the 10-problem benchmark harness is ready, but the benchmark environment must include `langchain<0.2>` for the current `sv-iv-analyze` dependency path
- the live multi-module CLI success path is still the main demo blocker

## Validated Runs On 2026-03-19

The following was exercised against the current `yaml-spec-refactor` branch state:

- `PYTHONPATH=. python3 apps/cli/cli.py --config config/runtime.yaml --spec-file tests/test_specs/demo_and2_structured.txt --yes --narrative-mode off --run-name demo_probe_and2_structured_v2`
  Result: `PASS`
  Notes: full engineer CLI path passed through planning, implementation, lint, TB generation, TB lint, simulation, and acceptance.

- `PYTHONPATH=. python3 apps/cli/cli.py --config config/scenarios/demo_multimodule.yaml --spec-file tests/test_specs/demo_inv1_wrapper_multimodule.txt --yes --narrative-mode off --run-name demo_probe_inv1_wrapper_multimodule`
  Result: first run `FAIL`, retry `PASS`
  Notes: the reduced wrapper-style multimodule example is the best current live candidate, but it is still not stable enough to call fully bulletproof. It passed end-to-end on retry.

- `PYTHONPATH=. python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign demo_readiness --run-id smoke10_20260319 --max-problems 10`
  Result: `PASS`
  Notes: canonical 10-problem VerilogEval slice passed `10/10` with summary artifacts under `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_20260319/`.

Additional negative results that matter for demo planning:

- `tests/test_specs/01_counter3_basic.txt` and `tests/test_specs/02_counter3_load.txt` both cleared planning and RTL generation but fell into downstream TB/debug problems, so they are not the safest live opening demo examples right now.
- `tests/test_specs/05_pwm_led_multimodule.txt` does not currently pass spec collection because it declares generated child nodes in top-level `L4.block_diagram` without corresponding child `Module:` sections.
- `tests/test_specs/complex_event_logger.txt` reached execution under the `L3` multimodule overlay but quickly fell into repeated child-module sim/debug churn, so it is not demo-safe.

## Readiness Matrix

| Demo Item | Readiness | Why It Is Reasonable To Demo | Main Risks | Recommended Demo Posture |
| --- | --- | --- | --- | --- |
| 3-bit counter with a filled spec through CLI | High | `tests/test_specs/01_counter3_basic.txt` currently passes cleanly first try end-to-end. | Broker, LLM, and tool dependencies must all be healthy. The CLI still pauses at `Proceed to execution?` unless `--yes` is passed. | Use `tests/test_specs/01_counter3_basic.txt`, pass `--yes`, and treat this as the anchor live run. |
| Simple multi-module design through CLI that passes | Low | The multimodule pipeline exists, but the currently prepared multimodule fixtures do not pass reliably in live retesting. | The current top-level multimodule flow falls into TB lint/sim/debug churn or fails collection outright. | Do not rely on a live multimodule pass unless you fix it first. If you keep this segment, use a prerecorded run or make it an honest “known remaining limitation” discussion. |
| 3-bit counter with a bad spec to show spec helper | Medium-High | The helper now asks plain-language clarification questions and keeps internal rigor labels hidden. | The interaction works, but the downstream run can still fall into TB/debug instability if you continue all the way through execution. | Use a narrowly incomplete spec, show 1-2 clarifications, and stop after the helper has repaired the spec unless the downstream path has been revalidated that day. |
| Benchmarking run with a limited set of problems | High | The 10-problem canonical slice passed `10/10` in the current retest. | The benchmark environment currently depends on `langchain<0.2` being present for `sv-iv-analyze`. | Either ensure that dependency is installed in the demo environment or precompute the benchmark artifacts and show the results. |
| Show AgentOps working and show costs for all runs | Medium for hosted AgentOps, High for local cost evidence | The tracker writes local cost and summary artifacts even when AgentOps is unavailable, and run-scoped observability paths are tested. | Hosted AgentOps depends on env setup, key availability, SDK availability, and network behavior. | Use local `artifacts/observability/...` as the primary proof. Treat the AgentOps dashboard as a bonus view. |

## Detailed Evaluation By Demo Segment

### 1. 3-Bit Counter With Filled Spec Through CLI

This is the strongest opening demo item.

Why it is demo-ready:

- `docs/cli.md` and `docs/workflows/interactive-run.md` both describe the engineer CLI flow as a first-class path.
- The CLI explicitly performs spec collection, planning, execution handoff, and orchestrated execution.
- The execution pipeline has passing automated coverage in `tests/execution/test_execution_pipeline.py`.

Main risks:

- the run still depends on RabbitMQ, LLM credentials, and local toolchain availability
- if you do it interactively without a prepared file, the opening can become slow
- if you do not pass `--yes`, the handoff prompt adds a pause

Recommendation:

- use `tests/test_specs/01_counter3_basic.txt` for the “good” 3-bit counter
- keep the design intentionally boring
- use the passing run to briefly show that the planner emitted a DAG and design context before execution

This is not just a good demo item. It should probably be the anchor of the whole demo.

### 2. Multi-Module CLI Design That Passes

This is demoable, but it is less safe than the single-module counter and should be treated accordingly.

Why it is reasonably demo-ready:

- `tests/cli/test_spec_flow_multimodule.py` covers multimodule spec-flow behavior, including multimodule collection and inventory validation
- `tests/execution/test_execution_pipeline.py` covers a multi-node execution fixture and passing pipeline behavior

Main risks:

- multimodule success is more dependent on planner/spec alignment
- a design that is “simple to understand” can still be unnecessarily hard for the current pipeline if the module boundaries are awkward
- if the example is too ambitious, the demo loses time in the wrong place

Recommendation:

- as of the latest retest, do not plan on a live multimodule success unless you fix and revalidate that path first
- if you keep the segment, either use a prerecorded successful run or present it as a clearly identified remaining limitation

Right now this is the only part of the proposed demo that is not substantively ready as a live end-to-end success path.

### 3. Bad 3-Bit Counter Spec To Demonstrate Spec Helper

This is worth showing, but it should be tightly staged.

Why it is worth including:

- it shows that the system is not only a happy-path generator
- it makes the spec helper legible to a non-specialist audience
- it helps explain why the spec stage exists at all

Current readiness caveat:

- the helper interaction itself is now human-facing and avoids internal rigor labels
- the remaining weakness is not the wording of the questions; it is whether you choose to continue into a full downstream execution run after the helper has repaired the spec

Main risks:

- if the spec is too bad, the interaction becomes long and unfocused
- if the helper asks an awkward question, the moment can feel less polished than the passing examples

Recommendation:

- keep the “bad” spec narrowly bad
- omit reset behavior, wraparound behavior, or enable semantics
- avoid making interface, behavior, and acceptance all ambiguous at once
- if the interaction is going well, let the helper recover the spec and then stop there
- do not feel obligated to turn the bad-spec segment into a full successful end-to-end run live

The goal of this segment should be “the helper improves the spec,” not “the entire pipeline runs again from scratch.”

### 4. Benchmark Run With A Limited Set Of Problems

This is viable, but it needs framing.

Why it is reasonably demo-ready:

- benchmark mode is a first-class CLI path with `run`, `analyze`, `compare`, and `list-problems`
- the workflow is documented in `docs/workflows/benchmark-run.md`
- `tests/apps/test_run_verilog_eval.py` has recent coverage around flow-mode selection, dry-run behavior, failure continuation, execution policy propagation, and direct vs orchestrated benchmark behavior

Important framing issue:

- the current default benchmark flow is `direct_single_module`
- that means benchmark mode is currently optimized as an evaluation path, not as a clean demonstration of the long-term intended shared planner/spec-helper path

That is not necessarily bad for the demo. It just needs to be explained honestly.

Main risks:

- benchmark mode has more prerequisites than the normal engineer flow
- the VerilogEval submodule, analyzer path, broker, and toolchain all matter
- run time can become noisy or unpredictable if the scope is not tiny

Recommendation:

- the current 10-problem canonical slice is passing, so the benchmark segment itself is in good shape
- the remaining caveat is environment packaging: the current app container needed `langchain<0.2>` installed for `sv-iv-analyze`
- if you want the benchmark segment to feel cleaner, do the real benchmark run beforehand and show the resulting `summary.txt`, `summary.csv`, and `aggregate.json`

This segment is best positioned as “we can evaluate the system on benchmark-style workloads,” not “this is the canonical architecture.”

### 5. AgentOps And Cost Visibility

This is worth showing, but the exact story should be split into two parts:

- local observability and cost artifacts
- hosted AgentOps dashboard, if available

Why the local story is strong:

- `docs/observability.md` clearly describes run-scoped observability outputs
- the tracker writes run-scoped `costs.jsonl` and `summary.json`
- `tests/core/test_observability_paths.py` covers run-scoped and legacy output emission

Why the hosted AgentOps story is weaker:

- the tracker only fully enables hosted AgentOps when `AGENTOPS_API_KEY` is present or `AGENTOPS_ENABLE=1`
- if AgentOps is not configured or the SDK is unavailable, the code degrades gracefully rather than hard-failing
- graceful degradation is good engineering, but it means the dashboard should not be the only thing you rely on in a live demo

Recommendation:

- use local observability artifacts as the guaranteed demo evidence
- use hosted AgentOps if it is already verified and working on demo day
- give every run a clear `--run-name` so the cost story is easy to follow afterward

For demo purposes, the strongest close is:

- show that every run emitted observable artifacts
- show that cost summaries exist
- then optionally show the AgentOps dashboard view for the same runs

## Is This A Good Demo?

Yes. The proposed demo is good because it shows five different strengths of the system:

- structured spec intake
- planning and execution
- multimodule handling
- recovery/help under bad input
- evaluation plus observability

What makes it risky is only the breadth, not the concept.

The most important adjustment I would make is this:

- do not treat every segment as equally live and equally critical

A better framing is:

- core live demo: good counter run, spec helper recovery
- controlled evaluation segment: tiny benchmark run or precomputed benchmark outputs
- observability close: local cost artifacts first, hosted AgentOps second

## Recommended Demo Order

I would recommend this order:

1. Good 3-bit counter through the engineer CLI
2. Very brief look at planner output (`dag.json` or printed node summary)
3. Bad 3-bit counter spec to show the spec helper correcting missing information
4. Small multi-module CLI example
5. Tiny benchmark run or benchmark dry-run plus prepared benchmark results
6. Observability and cost summary for all runs
7. AgentOps dashboard view if available

This order works better than ending with the spec helper because:

- the audience first sees the system succeed
- then sees how it handles imperfect input
- then sees broader capability
- then sees measurement and evidence

## Important Things To Show Explicitly

If there is one additional thing worth showing beyond your current list, it is the planning handoff artifact.

A very short glance at:

- printed DAG summary from the CLI
- `artifacts/generated/dag.json`
- `artifacts/generated/design_context.json`

helps prove that this is not just “prompt in, code out.” It shows that there is an explicit planning stage between spec collection and execution.

I would also make sure the demo audience sees at least one run-scoped observability directory, because that helps make the final cost/AgentOps section feel grounded rather than ornamental.

## Important Things Not To Rely On

I would avoid relying on these as live-only dependencies:

- a long benchmark run
- hosted AgentOps as the only cost story
- a brand new multi-module example that has not already passed at least once
- a “bad” spec that is bad in too many ways at the same time

## Demo-Day Preparation Checklist

### Environment

- run `PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.yaml`
- run `PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark`
- confirm broker connectivity
- confirm LLM credentials
- confirm `verilator`, `iverilog`, and `vvp`
- confirm benchmark submodule contents are present
- confirm AgentOps env vars if you want the hosted dashboard

### Demo Inputs

- freeze one known-good single-module counter spec file
- freeze one known-good simple multi-module spec file
- freeze one intentionally incomplete counter spec for the helper demo
- decide exact benchmark problem count ahead of time
- choose run names ahead of time so observability output is easy to narrate

### Suggested Run Naming

Use explicit run names such as:

- `demo_counter_good`
- `demo_counter_bad_spec`
- `demo_multimodule`
- `demo_benchmark`

That will make the observability and cost portion much easier to show.

## Suggested Scope Decision

If you want the safest version of the demo, I would scope it like this:

- live: good counter
- live: bad counter spec-helper recovery
- prerecorded or omitted: multi-module example unless it is revalidated first
- live or precomputed: benchmark
- live: local observability and cost files
- optional: hosted AgentOps dashboard

If you want the most impressive version of the demo, keep your current full list, but pre-run every exact artifact you intend to show and have the result directories ready as fallback.

## Evidence Checked For This Assessment

This evaluation was based on the current code/docs and targeted test coverage around the proposed demo surfaces.

Relevant docs checked:

- `docs/cli.md`
- `docs/workflows/interactive-run.md`
- `docs/workflows/benchmark-run.md`
- `docs/observability.md`

Relevant code paths checked:

- `apps/cli/cli.py`
- `apps/cli/spec_flow.py`
- `apps/cli/run_verilog_eval.py`
- `config/runtime.yaml`
- `core/observability/agentops_tracker.py`
- `core/observability/run_artifacts.py`

Relevant tests checked:

- `tests/cli/test_spec_flow_multimodule.py`
- `tests/apps/test_run_verilog_eval.py`
- `tests/core/test_observability_paths.py`
- `tests/orchestrator/test_orchestrator_service.py`
- `tests/execution/test_execution_pipeline.py`

Targeted test runs executed during this assessment:

- `pytest -q tests/cli/test_spec_flow_multimodule.py tests/apps/test_run_verilog_eval.py tests/core/test_observability_paths.py tests/orchestrator/test_orchestrator_service.py`
- `pytest -q tests/execution/test_execution_pipeline.py`

Observed result:

- `62 passed`
- one existing pytest warning about unknown config option `asyncio_mode`
