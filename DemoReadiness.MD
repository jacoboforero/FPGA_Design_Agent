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
- multi-module CLI pass: `Medium`
- bad-spec spec-helper showcase: `Medium`
- tiny benchmark run: `Medium-High`
- local cost/observability summary: `High`
- hosted AgentOps dashboard as a live dependency: `Medium`

The best version of this demo is:

- keep the live engineer examples very small
- keep the benchmark scope extremely small
- treat local observability artifacts as primary
- treat hosted AgentOps as a bonus, not the only way to show costs

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
| 3-bit counter with a filled spec through CLI | High | The engineer CLI flow is documented, the planner and execution checkpoints are documented, and the execution pipeline has passing automated coverage. | Broker, LLM, and tool dependencies must all be healthy. The CLI still pauses at `Proceed to execution?` unless `--yes` is passed. | Use a prepared known-good spec file, use `engineer_fast`, and pass `--yes`. |
| Simple multi-module design through CLI that passes | Medium | The multimodule spec flow has test coverage, and the execution pipeline has coverage for a multi-node DAG. | More moving parts than the single-module case. Success is more sensitive to planner/spec quality and design choice. | Keep the design very small, with 2-3 modules max, and pre-run the exact example you plan to show. |
| 3-bit counter with a bad spec to show spec helper | Medium | The helper loop is real and supports edit/chat/draft recovery while tracking missing fields. | Current UX still exposes legacy numbered-section wording and raw “missing fields” status. A badly chosen bad spec could create a long, messy interaction. | Make the spec incomplete but salvageable. Omit 1-2 important facts instead of making it chaotic. |
| Benchmarking run with a limited set of problems | Medium-High | Benchmark mode is documented, configurable, and has recent automated coverage for direct and orchestrated benchmark behavior plus run artifact generation. | Benchmark mode has more environment prerequisites. The current default path is `direct_single_module`, which is not the same thing as the long-term intended shared planner/spec-helper architecture. | Keep it tiny. Prefer `--max-problems 1` live, or at most `3` if pre-timed. Show dry-run first if useful. |
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

- use a prepared spec file for the “good” 3-bit counter
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

- use a multi-module example that is structurally simple rather than conceptually novel
- the best choice is probably a design that stays close to the counter theme so the instructor does not have to load a new mental model
- good candidates are a top module plus a small counter core plus a tiny terminal-count or decode helper

I would not use this segment to prove design complexity. I would use it to prove that the system can handle decomposition at all.

### 3. Bad 3-Bit Counter Spec To Demonstrate Spec Helper

This is worth showing, but it should be tightly staged.

Why it is worth including:

- it shows that the system is not only a happy-path generator
- it makes the spec helper legible to a non-specialist audience
- it helps explain why the spec stage exists at all

Current readiness caveat:

- the helper still thinks and talks in terms of the legacy numbered spec/checklist layout
- current CLI status text includes `missing fields remaining` and `Current section: <phase>`
- that is functionally useful, but it is not the clean future architecture you have documented elsewhere

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

- keep the live benchmark run to `--max-problems 1` if you want reliability
- use `list-problems` and `run --dry-run` as quick credibility steps if useful
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

- core live demo: good counter run, spec helper recovery, simple multi-module run
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
- live: tiny multi-module example only if already proven stable
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
