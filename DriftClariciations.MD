# Drift Clarifications

This document records clarifications about the intended architecture and places where the current code may have drifted from that intent.

The goal is to preserve intent in mostly the user's own words before more architectural changes are made.

## Why This Exists

There has been a lot of AI-assisted coding in this project and, over time, there has been some drift from the original intent to the actual code. Some of that drift was not fully visible until we traced the current implementation.

This document is meant to capture:

- what the intended behavior was,
- where the current code appears to differ,
- and where the intended behavior still needs to be clarified further.

## Configurations / YAML Setup + Commands / Running The Program

### Clarifications

Run configuration is a user-provided concern.

The YAML file does not just define a benchmark run. It configures a run period.

For the CLI, the user can configure most of the same things as well.

So the important point is not "benchmark YAML" specifically. The point is:

- run configuration is chosen by the user,
- it can come from YAML and, in many cases, from CLI options,
- and the system should not infer YAML or any other run-level configuration on its own.

The only intended per-spec inference is much simpler:

- the spec helper, whether interactive or non-interactive, should recognize if the design is single-module or multi-module,
- and it should include that distinction as part of the context passed to the planner agent.

Another clarification is that `spec_profile` and `verification_profile` are supposed to be separate concepts.

The intended separation is:

- `spec_profile` = spec-helper behavior + L1-L5 rigor/strictness
- `verification_profile` = execution/verification strategy

So `spec_profile` should not be where benchmark-vs-testbench verification strategy gets decided, and `verification_profile` should not be where spec-helper rigor gets decided.

### Current Code Reality

The current codebase appears to expose several overlapping ways of controlling or entering the system.

At a high level, the main current knobs and entry paths appear to be:

- preset-driven `spec_profile` / `verification_profile`,
- CLI choices such as `--spec-file` and `--direct-spec`,
- benchmark-specific runtime config such as benchmark flow selection,
- and separate entrypoints for full runs, spec-only flows, suites, and benchmark campaigns.

The current command/entrypoint landscape appears to include:

- a main full-pipeline CLI path,
- a spec-only CLI path,
- a benchmark CLI path,
- and auxiliary scripts such as suite/demo runners.

The current benchmark runner also appears to have multiple runtime behaviors:

- a planner/spec-driven path,
- a direct-context path,
- and a legacy lightweight path.

So even before deeper architectural drift, the current operational surface already looks more complex than the intended model.

### Drift Identified

The current CLI includes a `--direct-spec` path that parses L1-L5 structured text directly.

That appears to conflict with the intended behavior that L1-L5 is internal and the spec helper is always on.

The current system also appears to use preset/profile distinctions in a much less clean way than intended.

The observed behavior suggests:

- `engineer_fast` and `engineer_signoff` do not strongly differ in how the spec helper actually processes the spec,
- while `benchmark` swaps in a different algorithm entirely.

That appears to conflict with the intended meaning of spec profiles.

The current code also appears to mix benchmark behavior, testbench strategy, and spec-processing behavior in ways that make the architecture harder to reason about.

That appears to conflict with the intended idea that verification strategy should be controlled by `verification_profile` and not bleed into unrelated configuration or command behavior.

### Open Questions

The main configuration questions that still need to be clarified are:

- what each `spec_profile` is supposed to mean,
- which parts of the current preset system belong under `spec_profile`,
- which parts belong under `verification_profile`,
- and what, if anything, should remain configurable by CLI versus YAML while still representing the same run-level settings.

## Spec Helper

### Clarifications

The spec helper is always on.

There should not be a separate mode or command that explicitly says "spec helper".

The spec helper should have only two modes:

- `interactive`
- `non-interactive`

The distinction is intended to be very simple:

- `interactive` is for when the user wants to collaborate on the spec with the chatbot.
- `non-interactive` is for when the human just wants their spec to be used as is.

Current expectation:

- for now, the only time non-interactive behavior should happen is when the system is being benchmarked,
- not through the normal CLI path.

Another core clarification is that L1-L5 is an internal rigor structure, not a human-facing abstraction.

The L1-L5 spec was not meant to be an abstraction the human needs to worry about.

It was intended more as:

- a way to keep the level of rigor required internally by the spec helper agent,
- and a way to support different levels of strictness.

This means:

- there should not be any deterministic direct parsing of the L1-L5 spec as a user-facing mode,
- the human should not have to think in terms of "use L1-L5 mode" versus "do not use L1-L5 mode",
- and the system should treat L1-L5 as an internal representation managed by the spec helper.

There should also not be any deterministic direct parsing of L1-L5 spec text as a normal architectural path.

This includes the idea that a user can hand-author fully structured L1-L5 and the system simply bypasses the spec helper by parsing it directly.

That is considered drift from the intended design.

Another important clarification is that the only intended structural inference here is:

- recognize whether the design is single-module or multi-module,
- and pass that distinction to the planner.

The system is not supposed to infer YAML or more complex run-level configuration from the prompt/spec.

### Current Code Reality

The current code appears to have two different notions of "spec helper":

- a queue-based `SpecHelperWorker`,
- and a direct CLI-driven `spec_flow.py` path.

Normal CLI spec handling appears to go through `spec_flow.py` directly rather than through the queued `SpecHelperWorker`.

The current spec-processing landscape appears to include several actual code paths:

- direct parse of structured L1-L5-like input,
- interactive LLM-assisted checklist completion,
- non-interactive LLM-assisted checklist completion,
- multi-module spec collection,
- benchmark deterministic normalization,
- and benchmark direct-context bypass.

So the current code does not behave like a single always-on spec helper with only two modes. It behaves more like a collection of partially overlapping spec-processing paths.

### Drift Identified

The current benchmark flow includes deterministic benchmark normalization behavior.

That appears to conflict with the intended behavior that the spec helper should still exist in non-interactive mode rather than being replaced by deterministic normalization logic.

The existence of direct parse mode also appears to conflict with the intended behavior that the spec helper is always on and that L1-L5 is internal.

The current code also appears to treat benchmark behavior as a special algorithmic branch instead of a spec-helper mode distinction.

That appears to conflict with the intended simpler model where the spec helper always exists and the main difference is interactive vs non-interactive plus profile-driven rigor.

### Open Questions

The main spec-helper questions that still need to be clarified are:

- for each `spec_profile`, how strict or complete the internal representation should be,
- whether a profile should imply full L1-L5, partial/relaxed L1-L5, or no full L1-L5 at all,
- what the spec helper should save as its canonical output object,
- and what unresolved fields, assumptions, or open questions are allowed to survive into planning under each profile.

## Planner Agent

### Clarifications

The planner agent is intended to be an LLM-based agent.

It should be:

- independent from the execution phase of the system,
- unrelated to the orchestrator/queues/execution workers,
- and able to robustly generate the correct graph for us.

This means the planner should not just be a deterministic transform from frozen specs into a DAG/context artifact.

Another clarification is that the execution-facing context should be planner-owned and should not be generated deterministically.

The current idea of `design_context` is useful in principle, but it should not be something produced by deterministic projection logic.

Reasoning is required.

So the intended architecture is:

- the planner should own the production of the execution-facing context object,
- that context object should not be deterministically manufactured from frozen artifacts as the main path,
- and it should represent the planner's reasoning about the design, graph, interfaces, and node responsibilities.

This also means the same context-model question applies beyond benchmark mode.

There should not be one special context object design for "non-L1-L5/benchmarking" and a different conceptual contract elsewhere.

Instead, there should be one planner-owned execution/planning context model that can be populated differently depending on `spec_profile`.

In that model:

- `spec_profile` should affect how much structure, strictness, and certainty the planner receives,
- but it should not create a completely different internal contract for different workflows.

### Current Code Reality

The current queued planner worker appears to receive only a small context object containing things like:

- `spec_dir`,
- `out_dir`,
- and optional `execution_policy`.

It then appears to read frozen spec artifacts from disk and generate:

- `design_context.json`,
- and `dag.json`.

In other words, the current planner worker appears to behave like a wrapper around a deterministic transform from frozen artifacts to planning/execution artifacts.

The current benchmark behavior also appears split:

- in the planned/spec path, benchmark prompts are first normalized into synthetic L1-L5-like artifacts and then passed through the planner,
- while in the direct-context path, the planner is skipped entirely and `design_context` is built directly from the prompt/interface.

So the planner is currently both:

- more deterministic than intended,
- and not even the universal producer of execution context.

### Drift Identified

The current planner implementation appears to be a deterministic transform from frozen specs to `design_context.json` and `dag.json`.

That appears to conflict with the intended behavior that the planner agent should be LLM-based and responsible for robust graph generation.

The current code also appears to have two competing internal contracts:

- one path where frozen L1-L5 is turned deterministically into `design_context`,
- and another path where `design_context` is created directly without L1-L5.

That appears to conflict with the intended architecture.

What is actually needed is one clear planner-owned context contract rather than multiple incompatible ways of manufacturing execution context.

The current system also grew runner-level branches such as "direct context" versus "planned/spec context".

That appears to conflict with the intended simpler architecture where the spec helper identifies the design type and passes the right context to the planner.

### Open Questions

The main planner questions that still need to be clarified are:

- what context should be passed to the planner agent per `spec_profile`,
- what exact object the planner should consume,
- what exact object the planner should emit,
- whether the planner-owned execution context should remain called `design_context`,
- whether there should be a separate `plan_context` and `execution_context`,
- and what exact fields should always be present regardless of `spec_profile`.

## Orchestrator

### Clarifications

The execution phase and the planner phase are supposed to be conceptually separate.

The orchestrator is about execution.

The planner is about graph generation and decomposition.

Any naming that implies "orchestrated" means "multi-module" or "planned" is misleading, because orchestration belongs to execution, not planning.

The orchestrator should not be the thing that conceptually owns planning, decomposition, or graph generation.

### Current Code Reality

The current orchestrator appears to be the shared execution engine for the modern benchmark/runtime paths.

In particular:

- the direct-context benchmark path still uses the orchestrator,
- the planner/spec-driven benchmark path still uses the orchestrator,
- and the orchestrator is what advances nodes through implementation, lint, testbench, simulation, acceptance, reflection, and debug.

The main exception discussed so far is the legacy lightweight benchmark path, which appears to bypass the full orchestrated execution loop.

So the current distinction in code is not really "orchestrated vs not orchestrated" for the modern system. It is more like:

- which component produced the context that the orchestrator later executes.

### Drift Identified

The current use of terms like `orchestrated` is misleading.

The important distinction is not whether the execution is orchestrated.

The orchestrator runs the execution phase either way.

The actual distinction in the current code is closer to:

- direct prompt/spec-to-context generation,
- versus planner-mediated context generation.

So any naming that equates `orchestrated` with `multi-module` or with `planned` should be treated carefully.

### Open Questions

The main orchestrator-related question that still needs to be clarified is how explicit the boundary should be between:

- planner-owned artifacts and responsibilities,
- and orchestrator-owned execution responsibilities.

## Execution Phase Agents

### Clarifications

Another important clarification is that important meaning can get lost when the system translates the user's prompt/spec into internal structured context.

So the original prompt/spec should be preserved as a first-class object.

The intended behavior is that, in addition to whatever structured object gets extracted from the spec:

- the original prompt/spec text should still be available,
- and reasoning-heavy execution agents should receive it when it is useful.

At minimum, this should be evaluated for:

- implementation,
- testbench generation,
- debug,
- and reflection.

The point is not that these agents should ignore the structured context.

The point is that they should have both:

- the structured planner-owned context,
- and the original prompt/spec text,

so that information lost in translation does not become unrecoverable.

Another clarification is that execution-phase agents should consume planner-owned context, not raw spec-helper internals or an implicit dependence on frozen L1-L5 files.

### Current Code Reality

The execution-phase agents do not appear to consume raw L1-L5 files directly.

Instead, they appear to consume a derived per-node task context with fields such as:

- node identity,
- interface,
- RTL/testbench paths,
- clocking,
- behavior summary,
- verification and acceptance context,
- child/dependency wiring context,
- execution policy,
- and in some benchmark paths, the preserved original prompt.

So the current coupling is not "execution agents directly read L1-L5."

The current coupling is:

- execution agents depend on a derived execution context,
- and that derived context is often currently produced from L1-L5 or from benchmark-specific direct generation logic.

This means L1-L5 is not the literal runtime contract for execution agents today, but its semantics still leak into execution because the derived context is often built from it.

The current code also appears uneven in how it preserves and forwards the original prompt/spec:

- implementation and debug can use the raw benchmark prompt in some benchmark modes,
- but this does not appear to be a general rule across all reasoning agents and workflows.

### Drift Identified

The current code appears to preserve the original benchmark prompt in some benchmark paths, but not as a general architectural rule across all relevant agents and workflows.

That appears to conflict with the intended behavior that the original prompt/spec should remain available whenever structured translation may have lost important meaning.

The current code also appears to make execution agents depend on context that is often the result of deterministic projection from L1-L5 or special benchmark branches, rather than one clean planner-owned context contract.

That appears to conflict with the intended architecture.

### Open Questions

The main execution-phase-agent questions that still need to be clarified are:

- what exact context implementation/debug/testbench/reflection should receive,
- which reasoning agents should always receive the original prompt/spec text in addition to structured context,
- and how much of the planner-owned context should be node-local versus global/shared.

## Global Context That Multiple Agents Use

### Clarifications

There should be one planner-owned execution/planning context model that multiple agents can rely on.

That context model should be:

- consistent across workflows,
- capable of carrying the planner's structured interpretation of the design,
- and capable of preserving the original prompt/spec text where needed.

This context model should be able to exist under different `spec_profile` settings without changing the fundamental internal contract.

What should vary by profile is:

- how much structure is present,
- how strict or complete that structure is,
- and how much uncertainty the planner is allowed to inherit.

What should not vary by profile is:

- the existence of a shared planner-owned internal contract.

### Current Code Reality

The actual execution-phase requirement in the current code appears to be the shared context artifact often called `design_context`.

Today, that shared context seems to be produced in at least two different ways:

- frozen L1-L5-like artifacts are deterministically projected into `design_context`,
- or benchmark direct-context logic creates `design_context` directly without building full L1-L5 first.

This means L1-L5 is not actually the universal internal requirement in the current code.

What is currently universal for execution is closer to:

- "the system must eventually have a usable execution/planning context object."

Another important current-state observation is that `design_context` is not automatically safe from the same information-loss or strictness problems as L1-L5.

If `design_context` is derived from a lossy or over-normalized L1-L5-like representation, then those problems can carry forward into `design_context`.

The direct benchmark path avoids full L1-L5 generation, but it still appears to use heuristic/default context construction, so it is not automatically lossless either.

### Drift Identified

Right now the code appears to have multiple incompatible ways of manufacturing shared execution context.

That appears to conflict with the intended need for one clear shared internal context model.

The current code also appears to tie the quality of shared context too closely to deterministic L1-L5 projection in some paths and heuristic direct context generation in others.

That appears to conflict with the intended idea that reasoning should own the context that multiple agents depend on.

### Open Questions

The main global-context questions that still need to be clarified are:

- what representation gets persisted after the spec helper,
- what representation gets produced by the planner,
- what representation execution-phase agents consume,
- and what minimum shared fields must always exist even when a profile does not require full L1-L5.

## Short Summary Of Intended Architecture

In simplified form, the intended architecture is:

1. The spec helper is always on.
2. The spec helper has only two modes: interactive and non-interactive.
3. L1-L5 is internal and managed by the spec helper.
4. The spec helper should infer whether the design is single-module or multi-module.
5. That design-type context should be passed to an LLM-based planner agent.
6. The planner should generate the graph independent of execution concerns.
7. The orchestrator belongs only to execution.
8. `spec_profile` should control spec-helper handling and L1-L5 rigor.
9. `verification_profile` should independently control the verification strategy.
10. The original prompt/spec should be preserved alongside structured context where reasoning agents need it.
11. The planner should own the execution-facing context object, and it should not be produced deterministically as the main path.

## Immediate Follow-Up Questions

The most important areas to clarify next are:

- what each `spec_profile` is supposed to mean,
- for each `spec_profile`, whether the internal rigor is full L1-L5, partial L1-L5, or no full L1-L5,
- what exact object the spec helper should save,
- what exact object the planner should consume,
- what exact object the planner should emit,
- what exact context the execution-phase agents should receive,
- and which reasoning agents should always receive the original prompt/spec text in addition to structured context.

## Appendix: Current Observed Agent Context Snapshot

This appendix is included so future work can recover the high-level state we traced in the code, without having to rebuild the whole mental model from scratch.

### Shared Task / Result Contract

The current system appears to use a common queued task/result shape where:

- tasks carry a `context` dictionary plus routing metadata,
- and results carry status, logs, artifact paths, and optional reflection/distillation payloads.

### Spec Helper Worker

The queued spec helper worker appears to accept a draft-like input containing:

- raw spec text or behavior text,
- and optionally a partially filled checklist.

It appears to return:

- an updated checklist,
- and a list of missing fields/clarifications.

However, normal CLI spec handling does not appear to route through this worker today.

### Planner Worker

The current planner worker appears to receive only:

- a spec artifact directory,
- an output directory,
- and optional execution policy.

It appears to emit:

- `design_context.json`,
- and `dag.json`.

### Execution-Phase Shared Context

The current execution-phase node context appears to include things like:

- `node_id`,
- `interface`,
- `rtl_path` / `rtl_paths`,
- `tb_path`,
- `clocking`,
- `demo_behavior`,
- `verification`,
- `acceptance`,
- `execution_policy`,
- `benchmark_prompt` in some paths,
- `children`,
- `child_interfaces`,
- `connections`,
- and `module_contract`.

### Implementation / Testbench / Debug / Reflection

The reasoning-heavy execution agents currently appear to consume different slices of that shared context:

- implementation focuses on interface, behavior, clocking, verification, acceptance, and integration wiring,
- testbench focuses on interface, clocking, verification, and behavior summary,
- debug focuses on current artifacts plus logs, distilled data, reflection outputs, and execution policy,
- reflection focuses on distilled failure data, current code, and retry/stagnation metadata.

The original prompt/spec appears to be preserved only partially today:

- some benchmark implementation/debug paths can see the raw prompt,
- but this does not appear to be universal across all reasoning agents and workflows.

### Deterministic Workers

The deterministic workers appear to consume narrower structured subsets of the shared context:

- lint uses RTL paths and some contract information,
- TB lint uses RTL/TB paths plus interface/clocking semantics,
- simulation uses RTL/TB/oracle paths plus execution policy and verification scope,
- acceptance uses acceptance definitions and artifact paths,
- distillation uses node/attempt and task-memory artifacts.

### Key Catch-Up Observation

The most important overall observation from the code trace is:

- the current codebase is not organized around one clean always-on spec helper feeding one LLM planner feeding one planner-owned context contract.

Instead, it currently appears to mix:

- multiple spec-processing entry paths,
- a mostly deterministic planner path,
- a benchmark direct-context bypass,
- and partial raw-prompt preservation.

That is the central context behind the drift discussions in this document.
