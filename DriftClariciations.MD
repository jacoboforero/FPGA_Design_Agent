# Drift Clarifications

This document records clarifications about the intended architecture and places where the current code may have drifted from that intent.

The goal is to preserve intent in mostly the user's own words before more architectural changes are made.

## Table Of Contents

1. [Terminology Note](#terminology-note)
2. [Why This Exists](#why-this-exists)
3. [Intended Architecture](#intended-architecture)
   - Short Summary Of Intended Architecture
   - Configuration / Runtime Intent
   - Spec Helper Intent
   - Planner Intent
   - Orchestrator Intent
   - Execution-Phase Agent Intent
   - Shared Base Context Intent
4. [Current Code Reality And Drift](#current-code-reality-and-drift)
   - Configuration / Runtime
   - Spec Helper
   - Planner
   - Orchestrator
   - Execution-Phase Agents
   - Shared Base Context
5. [Per-Agent Input / Output Drift Analysis](#per-agent-input--output-drift-analysis)
6. [Consolidated Open Questions](#consolidated-open-questions)
   - Configuration / Runtime
   - Spec Helper
   - Planner
   - Orchestrator
   - Execution-Phase Agents
   - Shared Base Context
   - Highest-Priority Cross-Cutting Questions
7. [Appendix: Current Observed Agent Context Snapshot](#appendix-current-observed-agent-context-snapshot)

## Terminology Note

To keep this document readable, the intended terminology should be:

- `L0` through `L5` = rigor levels only.
- the old five-bucket stored shape formerly called `L1` through `L5` in parts of the code = the legacy numbered spec/checklist/artifact layout.

So when this document discusses:

- rigor, strictness, or `spec_profile.rigor_level`, `L0` through `L5` means the new rigor ladder,
- while phrases such as legacy numbered checklist, legacy numbered spec, or legacy numbered artifacts refer to the old content-bucket structure that should no longer be the canonical architecture.

## Why This Exists

There has been a lot of AI-assisted coding in this project and, over time, there has been some drift from the original intent to the actual code. Some of that drift was not fully visible until we traced the current implementation.

This document is meant to capture:

- what the intended behavior was,
- where the current code appears to differ,
- and where the intended behavior still needs to be clarified further.

## Intended Architecture

### Short Summary Of Intended Architecture

In simplified form, the intended architecture is:

1. The spec helper is always on.
2. The spec helper has only two modes: interactive and non-interactive.
3. The spec helper should own the canonical internal spec object rather than exposing a human-facing numbered checklist.
4. The spec helper should infer whether the design is single-module or multi-module.
5. That design-type context should be passed to an LLM-based planner agent.
6. The planner should generate the graph independent of execution concerns.
7. The orchestrator belongs only to execution.
8. `spec_profile` should consist of exactly two knobs: `interaction` and `rigor_level`.
9. `verification_profile` should independently control the verification strategy.
10. The original prompt/spec should be preserved alongside structured context where reasoning agents need it.
11. The planner should own the execution-facing context object, and it should not be produced deterministically as the main path.
12. The current intended rigor scale is `L0` through `L5`, with `L5` as the current highest needed level.
13. If numbered labels such as `L0`, `L1`, ..., `L5` are retained, they should describe rigor levels and not the names of the semantic spec sections.
14. The spec helper should always emit the canonical semantic spec object, regardless of rigor level.
15. The planner should consume that canonical semantic spec object rather than being designed around the current deterministic legacy numbered-artifact layout.
16. Benchmark and engineer flows should share the same internal spec-helper and planner contracts; they should differ only by `interaction`, `rigor_level`, and `verification_profile`.
17. The preserved original prompt/spec should be treated as a generic concept across both benchmark and CLI flows, not as a benchmark-only field.
18. A planner-owned base context contract should exist, but each execution-phase agent should receive only the projected subset and agent-specific artifacts it actually needs.
19. Execution-stage result contracts should also be normalized per stage rather than relying primarily on generic logs, generic `reflections`, and filesystem/path conventions.

### Configuration / Runtime Intent

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

- `spec_profile` = spec-helper behavior + rigor/strictness
- `verification_profile` = execution/verification strategy

So `spec_profile` should not be where benchmark-vs-testbench verification strategy gets decided, and `verification_profile` should not be where spec-helper rigor gets decided.

Another clarification under current discussion is that `spec_profile` should be simple and structured, not a loose label with hidden behavior.

The intended shape is:

- `interaction`: `interactive` or `non-interactive`
- `rigor_level`: `L0`, `L1`, `L2`, `L3`, `L4`, or `L5`

That means the clean intended configuration model is:

- `spec_profile` should resolve to exactly those two knobs,
- `verification_profile` should remain separate,
- and other behavior should be derived from those choices rather than introduced as additional overlapping spec-helper modes.

The current intended rigor ladder is:

- `L0`: minimal semantic spec object with ambiguities explicitly recorded
- `L1`: prompt-faithful extraction with limited assumptions
- `L2`: single-module planner-ready rigor
- `L3`: multi-module planner-ready rigor
- `L4`: build-ready rigor
- `L5`: signoff-ready rigor

For now, the intended highest level needed is `L5`.

### Spec Helper Intent

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

Another core clarification is that numbered levels such as `L0` through `L5` are intended to be internal rigor levels, not a human-facing abstraction.

The rigor ladder was not meant to be an abstraction the human needs to worry about.

It was intended more as:

- a way to keep the level of rigor required internally by the spec helper agent,
- and a way to support different levels of strictness.

This means:

- there should not be any deterministic direct parsing of the legacy numbered spec as a user-facing mode,
- the human should not have to think in terms of "use L-level mode" versus "do not use L-level mode",
- and the system should treat rigor as internal and managed by the spec helper.

There should also not be any deterministic direct parsing of legacy numbered-spec text as a normal architectural path.

This includes the idea that a user can hand-author a fully structured legacy numbered spec and the system simply bypasses the spec helper by parsing it directly.

That is considered drift from the intended design.

Another important clarification is that the only intended structural inference here is:

- recognize whether the design is single-module or multi-module,
- and pass that distinction to the planner.

The system is not supposed to infer YAML or more complex run-level configuration from the prompt/spec.

#### Separate Spec Sections From Rigor Levels

If configurable rigor levels are introduced, the current legacy `L1-L5` naming should not remain the canonical stored spec object.

The letter `L` originally implies "levels", so using `L1-L5` both for semantic content buckets and for strictness creates ambiguity and makes the architecture harder to reason about.

A cleaner intended model is:

- the spec helper should own one canonical internal spec object organized by semantic sections,
- likely core section names are `functional_intent`, `interface_contract`, `verification_plan`, `architecture_plan`, and `acceptance_contract`,
- supporting sections such as `metadata`, `uncertainty`, and `handoff` can exist alongside those core sections,
- rigor should be represented separately as an internal target level/profile,
- the current intended rigor scale is `L0` through `L5`,
- and if numbered labels such as `L0`, `L1`, ..., `L5` are kept at all, they should refer only to rigor levels and not to the semantic section names.

In that model, the spec helper should work like this:

- it should always extract and update the semantic spec object,
- it should evaluate that object against the target rigor policy for the chosen `spec_profile`,
- it should use single-module versus multi-module classification as part of that rigor policy, especially for architecture/dependency/connection requirements,
- in interactive mode, it should ask the next highest-priority clarification that blocks the target rigor,
- in non-interactive mode, it should make only the assumptions allowed by the target rigor, record those assumptions/open questions, and stop if the remaining gaps are not allowed to pass to planning,
- and planner handoff should be based on satisfying the rigor policy rather than on the idea that five numbered sections have all been deterministically completed.

Another important clarification is that the spec helper should always emit the same canonical semantic spec object regardless of rigor level.

`L0` should not mean "skip the semantic object and directly build execution context."

Instead, `L0` should mean:

- the semantic object can be sparse,
- uncertainties and assumptions must be stated honestly,
- and the planner is allowed to inherit more ambiguity.

This preserves the original intent that rigor is internal and configurable, while removing the ambiguity that comes from treating the same numbered labels as both content buckets and rigor levels.

### Planner Intent

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

There should not be one special context object design for benchmark/direct-context workflows and a different conceptual contract elsewhere.

Instead, there should be one planner-owned execution/planning context model that can be populated differently depending on `spec_profile`.

In that model:

- `spec_profile` should affect how much structure, strictness, and certainty the planner receives,
- but it should not create a completely different internal contract for different workflows.

Another clarification under current discussion is that the planner should consume the canonical semantic spec object produced by the spec helper.

The planner should not be designed around the current deterministic legacy numbered-artifact layout.

If temporary compatibility exports are needed while the codebase is being migrated, those are migration details and not part of the intended architecture.

The intended architecture is:

- spec helper produces canonical semantic spec object,
- planner consumes canonical semantic spec object,
- planner emits planner-owned execution/planning context,
- and execution agents consume planner-owned context.

### Orchestrator Intent

The execution phase and the planner phase are supposed to be conceptually separate.

The orchestrator is about execution.

The planner is about graph generation and decomposition.

Any naming that implies "orchestrated" means "multi-module" or "planned" is misleading, because orchestration belongs to execution, not planning.

The orchestrator should not be the thing that conceptually owns planning, decomposition, or graph generation.

### Execution-Phase Agent Intent

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

Another clarification is that execution-phase agents should consume planner-owned context, not raw spec-helper internals or an implicit dependence on frozen legacy numbered-spec files.

Another important clarification under current discussion is that "shared context" should not mean "one maximal execution payload that every execution-phase agent receives unchanged."

What is shared should be:

- a planner-owned base context contract,
- a preserved copy of the original prompt/spec text where needed,
- and stable identifiers/references that let agent-specific payloads be assembled consistently.

What should still vary by agent is:

- which subset of the shared context it actually receives,
- which additional agent-specific artifacts it receives,
- and how much history/evidence is appropriate for that agent's task without wasting tokens.

For example:

- implementation may need interface, architecture, planner intent, and the original spec text,
- testbench may need interface, verification goals, clocking, acceptance targets, and the original spec text,
- debug may need shared planner context plus current code, failure logs, simulation outputs, and reflection/distillation artifacts,
- and reflection may need shared planner context plus failure evidence, retry history, and current artifacts.

So the intended architecture is:

- one planner-owned base context contract,
- plus per-agent projected payloads built from that contract,
- plus agent-specific evidence/artifacts where appropriate.

In other words, the intended architecture is not:

- one giant global execution-phase payload copied to every agent.

The intended architecture is:

- one canonical planner-owned base object,
- per-agent projection rules that choose the smallest useful slice for that agent,
- and extra agent-specific inputs added only when that agent actually needs them.

### Shared Base Context Intent

There should be one planner-owned execution/planning base context model that multiple agents can rely on.

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

- the existence of a planner-owned base internal contract.

Another clarification under current discussion is that benchmark and engineer flows should share that same internal contract.

So the intended architecture is not:

- one path where benchmark builds execution context directly,
- and another path where engineer flow goes through spec-helper plus planner.

The intended architecture is:

- both flows should ultimately go through the same spec-helper output contract,
- both flows should ultimately go through the same planner-owned context contract,
- and differences between them should come from `interaction`, `rigor_level`, and `verification_profile`, not from incompatible internal object shapes.

Another clarification under current discussion is that a planner-owned base context contract does not imply one maximal task payload for all execution agents.

The intended architecture is:

- the planner owns one base internal context contract,
- execution-phase agents receive projected slices of that base contract,
- the original prompt/spec text is preserved under a generic field/concept that applies to both benchmark and CLI flows,
- and agent-specific evidence/artifacts are added on top of the projected shared slice when needed.

## Current Code Reality And Drift

### Configuration / Runtime

#### Current Code Reality

The current codebase appears to expose several overlapping ways of controlling or entering the system.

At a high level, the main current knobs and entry paths appear to be:

- run-policy-driven `spec_profile` / `verification_profile`,
- CLI choices such as `--spec-file`,
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

#### Drift Identified

The public CLI no longer exposes `--direct-spec`, which matches the intended behavior that rigor handling is internal, the legacy numbered shape is not a first-class user-facing contract, and the spec helper is always on.

The main remaining complexity in this area appears to be benchmark flow branching and the continued coexistence of multiple auxiliary entrypoints around the core CLI path.

The current code also appears to mix benchmark behavior, testbench strategy, and spec-processing behavior in ways that make the architecture harder to reason about.

That appears to conflict with the intended idea that verification strategy should be controlled by `verification_profile` and not bleed into unrelated configuration or command behavior.

### Spec Helper

#### Current Code Reality

The current code appears to have two different notions of "spec helper":

- a queue-based `SpecHelperWorker`,
- and a direct CLI-driven `spec_flow.py` path.

Normal CLI spec handling appears to go through `spec_flow.py` directly rather than through the queued `SpecHelperWorker`.

The current spec-processing landscape appears to include several actual code paths:

- direct parse of structured legacy numbered-spec input,
- interactive LLM-assisted checklist completion,
- non-interactive LLM-assisted checklist completion,
- multi-module spec collection,
- benchmark deterministic normalization,
- and benchmark direct-context bypass.

So the current code does not behave like a single always-on spec helper with only two modes. It behaves more like a collection of partially overlapping spec-processing paths.

#### Drift Identified

The current benchmark flow includes deterministic benchmark normalization behavior.

That appears to conflict with the intended behavior that the spec helper should still exist in non-interactive mode rather than being replaced by deterministic normalization logic.

The existence of direct parse mode also appears to conflict with the intended behavior that the spec helper is always on and that rigor is internal rather than exposed through a legacy numbered-spec mode.

The current code also appears to treat benchmark behavior as a special algorithmic branch instead of a spec-helper mode distinction.

That appears to conflict with the intended simpler model where the spec helper always exists and the main difference is interactive vs non-interactive plus profile-driven rigor.

### Planner

#### Current Code Reality

The current queued planner worker appears to receive only a small context object containing things like:

- `spec_dir`,
- `out_dir`,
- and optional `execution_policy`.

It then appears to read frozen spec artifacts from disk and generate:

- `design_context.json`,
- and `dag.json`.

In other words, the current planner worker appears to behave like a wrapper around a deterministic transform from frozen artifacts to planning/execution artifacts.

The current benchmark behavior also appears split:

- in the planned/spec path, the original prompt/spec input is first normalized into synthetic legacy numbered-spec artifacts and then passed through the planner,
- while in the direct-context path, the planner is skipped entirely and `design_context` is built directly from the prompt/interface.

So the planner is currently both:

- more deterministic than intended,
- and not even the universal producer of execution context.

#### Drift Identified

The current planner implementation appears to be a deterministic transform from frozen specs to `design_context.json` and `dag.json`.

That appears to conflict with the intended behavior that the planner agent should be LLM-based and responsible for robust graph generation.

The current code also appears to have two competing internal contracts:

- one path where frozen legacy numbered artifacts are turned deterministically into `design_context`,
- and another path where `design_context` is created directly without that legacy numbered layer.

That appears to conflict with the intended architecture.

What is actually needed is one clear planner-owned context contract rather than multiple incompatible ways of manufacturing execution context.

The current system also grew runner-level branches such as "direct context" versus "planned/spec context".

That appears to conflict with the intended simpler architecture where the spec helper identifies the design type and passes the right context to the planner.

### Orchestrator

#### Current Code Reality

The current orchestrator appears to be the shared execution engine for the modern benchmark/runtime paths.

In particular:

- the direct-context benchmark path still uses the orchestrator,
- the planner/spec-driven benchmark path still uses the orchestrator,
- and the orchestrator is what advances nodes through implementation, lint, testbench, simulation, acceptance, reflection, and debug.

The main exception discussed so far is the legacy lightweight benchmark path, which appears to bypass the full orchestrated execution loop.

So the current distinction in code is not really "orchestrated vs not orchestrated" for the modern system. It is more like:

- which component produced the context that the orchestrator later executes.

#### Drift Identified

The current use of terms like `orchestrated` is misleading.

The important distinction is not whether the execution is orchestrated.

The orchestrator runs the execution phase either way.

The actual distinction in the current code is closer to:

- direct prompt/spec-to-context generation,
- versus planner-mediated context generation.

So any naming that equates `orchestrated` with `multi-module` or with `planned` should be treated carefully.

### Execution-Phase Agents

#### Current Code Reality

The execution-phase agents do not appear to consume raw legacy numbered-spec files directly.

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

So the current coupling is not "execution agents directly read the legacy numbered spec."

The current coupling is:

- execution agents depend on a derived execution context,
- and that derived context is often currently produced from the legacy numbered spec/checklist layer or from benchmark-specific direct generation logic.

This means the legacy numbered spec is not the literal runtime contract for execution agents today, but its semantics still leak into execution because the derived context is often built from it.

The current code also appears uneven in how it preserves and forwards the original prompt/spec:

- implementation and debug can use the raw original prompt/spec in some benchmark modes,
- but this does not appear to be a general rule across all reasoning agents and workflows.

#### Drift Identified

The current code appears to preserve the original prompt/spec in some benchmark paths, but not as a general architectural rule across all relevant agents and workflows.

That appears to conflict with the intended behavior that the original prompt/spec should remain available whenever structured translation may have lost important meaning.

The current code also appears to make execution agents depend on context that is often the result of deterministic projection from the legacy numbered spec/checklist layer or special benchmark branches, rather than one clean planner-owned context contract.

That appears to conflict with the intended architecture.

### Shared Base Context

#### Current Code Reality

The actual execution-phase requirement in the current code appears to be the shared context artifact often called `design_context`.

Today, that shared context seems to be produced in at least two different ways:

- frozen legacy numbered-spec artifacts are deterministically projected into `design_context`,
- or benchmark direct-context logic creates `design_context` directly without building the full legacy numbered layer first.

This means the legacy numbered spec/checklist layer is not actually the universal internal requirement in the current code.

What is currently universal for execution is closer to:

- "the system must eventually have a usable execution/planning context object."

Another important current-state observation is that `design_context` is not automatically safe from the same information-loss or strictness problems as the legacy numbered-spec layer.

If `design_context` is derived from a lossy or over-normalized legacy numbered-spec representation, then those problems can carry forward into `design_context`.

The direct benchmark path avoids full legacy numbered-spec generation, but it still appears to use heuristic/default context construction, so it is not automatically lossless either.

#### Drift Identified

Right now the code appears to have multiple incompatible ways of manufacturing shared execution context.

That appears to conflict with the intended need for one clear shared internal context model.

The current code also appears to tie the quality of shared context too closely to deterministic projection from the legacy numbered-spec layer in some paths and heuristic direct context generation in others.

That appears to conflict with the intended idea that reasoning should own the context that multiple agents depend on.

## Per-Agent Input / Output Drift Analysis

This section is included to capture the current state of the per-agent and per-worker inputs/outputs in the codebase, compared against the likely intended architecture implied by the clarifications above.

The "optimal" descriptions below are not meant as a separate new plan.

They are the most coherent interpretation of the intended architecture already clarified in this document:

- one planner-owned base context contract,
- per-agent projected payloads,
- preserved original prompt/spec where useful,
- and agent-specific evidence/artifacts layered on top only when needed.

### Current Projection Pattern

Before looking at each agent individually, the most important current-state observation is that execution currently does not appear to use intentionally minimized per-agent payloads.

Instead, most execution tasks appear to start from one shared `DemoContextBuilder.build()` payload containing fields such as:

- `node_id`,
- `interface`,
- `rtl_path`,
- `rtl_paths`,
- `tb_path`,
- `oracle_ref_path`,
- `design_context_hash`,
- `coverage_goals`,
- `clocking`,
- `library_refs`,
- `demo_behavior`,
- `verification`,
- `acceptance`,
- `verification_scope`,
- `execution_policy`,
- preserved original prompt/spec text under benchmark-specific naming in some paths,
- `top_module`,
- `children`,
- `child_interfaces`,
- `connections`,
- and `module_contract`.

The orchestrator then appears to add only small stage-specific overlays:

- `attempt` on retry-sensitive stages,
- `debug_reason`, `attempt_history`, and stagnation flags for debug,
- `attempt_history` and stagnation flags for reflection,
- and near-miss retry metadata for some debug paths after simulation failure.

So the current execution architecture appears closer to:

- one broad shared superset payload,
- plus a few stage overlays,
- rather than one planner-owned base contract with intentionally projected minimal payloads per agent.

That appears to be a meaningful drift from the intended architecture.

### Spec Helper

- Optimal input: raw prompt/spec text, clarification history, current semantic spec draft, `interaction`, and target `rigor_level`.
- Optimal output: canonical semantic spec object, explicit assumptions/open questions, rigor gaps, and handoff readiness.
- Current input: `spec.spec_text` or `spec.behavior` or `spec_text`, plus an optional partially filled checklist.
- Current output: a successful result whose `reflections` field contains JSON with `status`, `missing_fields`, and an updated checklist.
- Drift: the runtime contract still appears checklist-first and legacy-numbered-checklist-shaped, and the output is tunneled through a generic `reflections` field rather than a dedicated canonical spec artifact/result contract.

### Planner

- Optimal input: canonical semantic spec object, preserved original prompt/spec text where useful, rigor metadata, and explicit uncertainty/assumption state.
- Optimal output: graph plus the planner-owned base execution context contract, including unresolved assumptions that downstream agents may need to see.
- Current input: `spec_dir`, `out_dir`, and optional `execution_policy`.
- Current output: filesystem artifacts `design_context.json` and `dag.json`, with only `artifacts_path` and a summary log returned in the queue result.
- Drift: the planner contract appears filesystem-oriented and opaque, not a first-class structured planner input/output contract, and it still behaves like a wrapper around deterministic transforms.

### Implementation Agent

- Optimal input: node-local design intent, interface contract, module contract/style constraints, child interfaces/connections only if the node is an integration node, language/tool policy, and preserved original prompt/spec text or a precise semantic excerpt when helpful.
- Optimal output: generated RTL artifact plus structured notes on assumptions made, important design choices, and any unresolved risk relevant to downstream stages.
- Current input: a broad shared payload including `rtl_path`, `interface`, `clocking`, `verification`, `acceptance`, `execution_policy`, `demo_behavior`, benchmark-specific preserved prompt naming in some paths, `children`, `child_interfaces`, `connections`, and `module_contract`.
- Current output: writes RTL to disk and returns `artifacts_path` plus an unstructured summary log.
- Drift: the input is broader than necessary, it still depends on benchmark-specific naming for preserved raw prompt/spec text, and the output does not preserve structured implementation assumptions or reasoning for downstream consumers.

### Testbench Agent

- Optimal input: node-local interface contract, normalized clock/reset contract, verification intent, acceptance targets only where they materially affect checking, current RTL artifact reference, and preserved original prompt/spec text when verification intent would otherwise be underspecified.
- Optimal output: generated testbench artifact plus structured notes on checker strategy, oracle assumptions, and any intentionally deferred coverage.
- Current input: `node_id`, `rtl_path`, `tb_path`, `interface`, `top_module`, `verification`, `demo_behavior`, and `clocking`.
- Current output: writes the TB to disk and returns `artifacts_path` plus an unstructured log.
- Drift: this is narrower than implementation already, but it appears to have no general path for preserved original prompt/spec text, even though it is a reasoning-heavy agent that may also lose meaning if only `demo_behavior` and the normalized verification fields survive.

### RTL Lint Worker

- Optimal input: RTL artifact references plus only the lint-relevant semantic contract needed for additional structural checks.
- Optimal output: pass/fail status plus structured semantic and tool diagnostics.
- Current input: effectively `rtl_path`, `rtl_paths`, and `module_contract`, although it is still invoked with the much broader shared payload.
- Current output: `artifacts_path` pointing to RTL plus a text log.
- Drift: the worker itself is relatively lean, but the task projection is not; its output is also log-centric rather than a structured lint finding object.

### Testbench Lint Worker

- Optimal input: RTL artifact refs, TB artifact ref, interface signal names, and normalized clock/reset semantics.
- Optimal output: pass/fail status plus structured semantic findings for race/reset/checker issues.
- Current input: effectively `rtl_path`, `tb_path`, `rtl_paths`, `interface`, and `clocking`, but again it receives the broad shared payload.
- Current output: `artifacts_path` pointing to the TB plus a text log.
- Drift: similar to RTL lint, the worker logic is narrower than the projected task payload, and semantic results are emitted only as text.

### Simulation Worker

- Optimal input: RTL refs, TB ref, optional oracle ref, run/attempt metadata, and simulation policy/tool settings.
- Optimal output: structured simulation result including pass/fail, failure cycle/time if known, mismatch summary if relevant, and explicit waveform/artifact refs.
- Current input: effectively `rtl_path`, `rtl_paths`, `tb_path`, `oracle_ref_path`, `node_id`, `attempt`, `execution_policy`, and `verification_scope`.
- Current output: a text log plus optional waveform path in `artifacts_path`.
- Drift: the input needs are already much narrower than the current shared superset projection, and the output remains mostly log-text that later stages re-parse instead of receiving a first-class structured failure summary.

### Acceptance Worker

- Optimal input: explicit acceptance contract, explicit artifact manifest/metric sources, and a normalized simulation outcome summary.
- Optimal output: pass/fail decision plus structured unmet criteria and deferred criteria.
- Current input: `node_id`, `attempt`, `acceptance`, `execution_policy`, `verification_scope`, and artifact refs such as `rtl_path`, `rtl_paths`, and `tb_path`.
- Current output: a pass/fail text log with no dedicated structured acceptance result object.
- Drift: the worker relies on path conventions and re-reading task-memory artifacts rather than receiving a cleaner artifact manifest and normalized upstream summaries.

### Distillation Worker

- Optimal input: explicit simulation artifact refs and metadata for the failed attempt, especially the relevant log/waveform locations.
- Optimal output: a structured distilled failure package suitable for reflection and debug.
- Current input: effectively only `node_id` and `attempt`; everything else is recovered from task-memory naming conventions.
- Current output: a structured `distilled_dataset` object plus the persisted distilled JSON file.
- Drift: the output shape is closer to the intended architecture than many other stages, but the input contract is too implicit and depends heavily on filesystem conventions rather than explicit upstream artifact references.

### Reflection Agent

- Optimal input: distilled failure package, current RTL/TB refs, attempt history/stagnation state, relevant verification context, and preserved original prompt/spec text when it would materially help interpret intent.
- Optimal output: structured reflection insights plus a compact debug-oriented hypothesis/probe package.
- Current input: `node_id`, `attempt`, `rtl_path`, `tb_path`, `coverage_goals`, `attempt_history`, and stagnation flags, while the actual distilled dataset is loaded by convention from task memory.
- Current output: structured `reflection_insights`.
- Drift: this is one of the stronger current outputs, but the input still depends on implicit task-memory lookup and does not appear to consistently include preserved original prompt/spec text or richer structured design intent.

### Debug Agent

- Optimal input: current RTL/TB, node-local design contract, preserved original prompt/spec text or precise semantic excerpt, failure evidence, distilled/reflection outputs, attempt history/stagnation state, and only the tool/lint policy needed for local validation.
- Optimal output: structured patch result identifying what changed, why it changed, what validation passed, and which artifacts downstream stages should treat as updated.
- Current input: `node_id`, `rtl_path`, `tb_path`, `attempt`, `debug_reason`, `execution_policy`, benchmark-specific preserved prompt naming in some paths, `demo_behavior`, `rtl_paths`, `module_contract`, `interface`, and `clocking`, while logs, distilled data, and reflection outputs are loaded from task memory by convention.
- Current output: patches artifacts in place, returns `artifacts_path` pointing to RTL, and stores structured patch metadata inside the generic `reflections` field.
- Drift: this agent is closest to the intended "projected shared context plus agent-specific evidence" model, but it still depends on benchmark-specific raw-prompt naming, implicit task-memory conventions, and an overloaded `reflections` field; its `artifacts_path` is also asymmetric because it still points to RTL even when a TB-only patch is produced.

### High-Level Drift Summary

The most important per-agent I/O drift appears to be:

- the current orchestrator sends most stages a broad shared superset payload instead of intentional per-agent projections,
- several reasoning agents still rely on `demo_behavior` or benchmark-specific prompt naming rather than one generic preserved original prompt/spec concept,
- some of the most useful downstream outputs are still tunneled through generic fields like `reflections` or plain text logs,
- multiple stages recover critical evidence by re-reading task-memory paths by convention instead of consuming explicit upstream artifact/result references,
- and the current result contracts are inconsistent across stages, which makes it harder to define one clean planner-owned execution context contract plus clean downstream projections.

## Consolidated Open Questions

### Configuration / Runtime

The main configuration questions that still need to be clarified are:

- how exactly the two-knob `spec_profile` should be represented in YAML/CLI/runtime types,
- which legacy preset behaviors should be deleted rather than carried forward,
- which parts belong under `verification_profile`,
- and what, if anything, should remain configurable by CLI versus YAML while still representing the same run-level settings.

### Spec Helper

The main spec-helper questions that still need to be clarified are:

- the exact field-by-field rigor policy for `L0` through `L5`,
- the exact canonical schema for the semantic spec object,
- and what unresolved fields, assumptions, or open questions are allowed to survive into planning under each rigor level.

### Planner

The main planner questions that still need to be clarified are:

- what exact canonical semantic spec object should be passed to the planner agent,
- what planner-visible uncertainty/assumption structure should always be included,
- what exact object the planner should consume,
- what exact object the planner should emit,
- whether the planner-owned execution context should remain called `design_context`,
- whether there should be a separate `plan_context` and `execution_context`,
- and what exact fields should always be present regardless of `spec_profile`.

### Orchestrator

The main orchestrator-related question that still needs to be clarified is how explicit the boundary should be between:

- planner-owned artifacts and responsibilities,
- and orchestrator-owned execution responsibilities.

### Execution-Phase Agents

The main execution-phase-agent questions that still need to be clarified are:

- what exact minimal planner-owned base fields should always exist,
- what exact projected context implementation/debug/testbench/reflection should each receive,
- what agent-specific artifacts/evidence should be attached beyond that shared context,
- which reasoning agents should always receive the original prompt/spec text in addition to structured context,
- and how much of the planner-owned context should be node-local versus shared/base.

### Shared Base Context

The main global-context questions that still need to be clarified are:

- what representation gets persisted after the spec helper,
- what representation gets produced by the planner,
- what representation execution-phase agents consume,
- and what minimum shared fields must always exist even when a profile does not require high-rigor semantic completeness.

### Highest-Priority Cross-Cutting Questions

The most important areas to clarify next are:

- what exact YAML/runtime representation should be used for the two-knob `spec_profile`,
- what exact field-by-field rigor policy should be used for `L0` through `L5`,
- what exact semantic object the spec helper should save,
- what exact object the planner should consume,
- what exact object the planner should emit,
- what exact context the execution-phase agents should receive,
- what exact structured result contract each execution-stage agent/worker should emit,
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
- preserved original prompt/spec text in some paths (currently benchmark-specific naming exists in parts of the code),
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

This further supports the intended architecture that per-agent payloads should be projected intentionally rather than copied wholesale from one global superset object.

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
