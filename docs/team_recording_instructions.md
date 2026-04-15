# Team Recording Instructions For Showcase Video

Copy and paste this to the team if you want.

---

We are building the showcase video around what is most impressive and important, not around long workflow tutorials.

That means each person should record short clips that answer:

1. What did I build?
2. Why does it matter?
3. What proof visual best shows it?

Each person needs to send me `3` raw files:

1. `NAME_impact.mp4`
2. `NAME_proof_intro.mp4`
3. `NAME_proof_visual.mov` or `NAME_proof_visual.mp4`

Please send raw clips only. I will edit them.

## General Recording Rules

- Record in `landscape`.
- Use `1080p` if possible.
- Frame yourself from mid-torso upward.
- Put the camera at eye level.
- Face a light source.
- Use a quiet room.
- Speak clearly and stay close to the microphone.
- Wear casual-professional clothing.
- Leave `2` seconds before speaking and `2` seconds after.
- Do not say `today`, `this semester`, or other relative dates.
- Keep your tone confident and direct.
- Do not explain a long workflow. Focus on what is novel or important.

## File 1: Impact Clip

Length:

- `12` to `18` seconds

Purpose:

- say what you built
- say why it matters

### Jacobo - Impact Clip

> Hi, I'm Jacobo Forero, and I led agent orchestration and user-facing interfaces for the project. That matters because multi-agent systems only become useful when dependencies, handoffs, and execution order are explicit.

### Dexter - Impact Clip

> Hi, I'm Dexter Pressley, and I worked on LLM interoperability across the platform. That matters because a serious platform should not be locked to one provider or one model if you want vendor flexibility and meaningful comparisons.

### Andrew - Impact Clip

> Hi, I'm Andrew Chambers, and I led benchmarking and evaluation for the project. That matters because systems like this should be judged on measurable results, not just handpicked demos.

### Sammy - Impact Clip

> Hi, I'm Sammy Fares, and I built the retrieval-augmented generation component. That matters because engineering workflows benefit from reusable prior knowledge, especially in multi-module design work.

### Caleb - Impact Clip

> Hi, I'm Caleb Elliott, and I worked on observability and cost accounting for the platform. That matters because teams need traceability into how a run behaved, not just whether it produced output.

### Matheus - Impact Clip

> Hi, I'm Mateus Verffel Mayer, and I worked on tooling, environment integration, and EDA connectivity. That matters because an agent system becomes much more useful when it can actually drive real engineering tools.

## File 2: Proof Intro Clip

Length:

- `7` to `10` seconds

Purpose:

- set up your proof visual

### Jacobo - Proof Intro

> I will show the planning artifacts that make multi-module orchestration explicit.

### Dexter - Proof Intro

> I will show the configuration layer that makes the system model-agnostic.

### Andrew - Proof Intro

> I will show the benchmark artifacts that turn this into a research platform.

### Sammy - Proof Intro

> I will show how retrieval is grounded in stored design memory.

### Caleb - Proof Intro

> I will show the run summaries that expose tokens, cost, and execution evidence.

### Matheus - Proof Intro

> I will show how the platform is wired into real EDA tooling.

## File 3: Proof Visual

Length:

- `10` to `20` seconds

Purpose:

- one clear proof artifact
- not a full walkthrough

Important:

- use large text or zoom in
- move slowly
- avoid tiny terminal fonts
- if a screenshot is better than a full recording, that is fine

### Jacobo - Proof Visual

Show:

- `artifacts/generated/dag.json`
- `artifacts/generated/design_context.json`

Suggested narration:

> This shows that the system turns the spec into an explicit dependency graph and structured design context before execution starts.

### Dexter - Proof Visual

Show:

- `config/domains/agents.yaml`

Suggested narration:

> This configuration is the proof that provider, model, and per-role settings can be changed without rebuilding the system around one backend.

### Andrew - Proof Visual

Show:

- `artifacts/benchmarks/verilog_eval/canonical_full_156/aggregate.json`
- `artifacts/benchmarks/verilog_eval/demo_readiness/smoke10_20260323_retest2/canonical/aggregate.json`

Suggested narration:

> These aggregate artifacts are the proof that the platform is benchmarkable, with both larger-scale stored results and smaller reproducibility slices.

### Sammy - Proof Visual

Show:

- `artifacts/rag/memory.json`
- optional short run clip with `--rag on`

Suggested narration:

> This is the stored design memory that retrieval can bring back into the engineering workflow when it is useful.

### Caleb - Proof Visual

Show:

- `artifacts/observability/demo_retest_counter3_basic_20260323_summary.json`
- `artifacts/observability/benchmark_demo_readiness_smoke10_20260323_retest2_canonical_summary.json`

Suggested narration:

> These summaries are the proof that we record concrete token and cost evidence at run scope instead of relying on vague impressions.

### Matheus - Proof Visual

Show:

- `tool_registry.yaml`
- optional terminal or log clip with `iverilog`, `vvp`, or `verilator`

Suggested narration:

> This tooling layer is the proof that the platform connects to real EDA tools rather than stopping at text generation.

## Recording Method

### Talking-head clips

Use whichever is easiest:

- phone camera in landscape
- laptop webcam
- OBS if you already use it

### Screen or proof visuals on Mac

Use:

- `QuickTime Player -> File -> New Screen Recording`

If a static screenshot is enough, just send the screenshot and I can animate it in editing.

### Screen or proof visuals on PC

Use:

- `OBS`

## Delivery

Please upload your `3` files with these exact names:

- `jacobo_impact.mp4`
- `jacobo_proof_intro.mp4`
- `jacobo_proof_visual.mov`
- `dexter_impact.mp4`
- `dexter_proof_intro.mp4`
- `dexter_proof_visual.mov`
- and so on for everyone else

If your proof visual exports as `mp4` instead of `mov`, that is fine.

## What Not To Do

- do not record vertically
- do not improvise a long explanation
- do not spend 30 seconds typing commands
- do not add music
- do not add captions
- do not trim clips aggressively
- do not send edited montage videos

## Safety Net

If you mess up, pause and restart the sentence.

If you are unsure whether a proof visual is good enough, send it anyway. I can replace weak visuals with my own captured screenshots if needed.

---

If needed, I can reduce this into an even shorter Slack-ready version.
