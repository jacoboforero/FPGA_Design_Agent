# Runtime Config Reference

Last verified against runtime behavior: March 19, 2026.

Runtime config is loaded from YAML manifests. The normal entrypoints are:

- `config/runtime.yaml` for engineer runs
- `config/runtime.benchmark.yaml` for benchmark runs

Use `--config` to choose which manifest to load.

## What This Page Is For
Use this page to understand which config files matter, which ones are normal entrypoints, and which runtime sections materially change system behavior.

## What This Page Is Not For
- It is not a full schema dump of every nested field.
- It is not a command runbook; use workflow pages for command sequences.

## Mental Model
The config directory is intentionally split by concern:

- root manifests choose which files to include
- run-policy files choose engineer versus benchmark behavior
- shared domain files hold broker, CLI, agent, verification, and benchmark settings
- scenario manifests are thin overlays for specific campaigns or tests

If you want the simplest possible mental model, ignore everything except:

- `config/runtime.yaml`
- `config/runtime.benchmark.yaml`

Those are the two normal user-facing manifests.

## Config Files In `config/`

### Canonical entry manifests
- `config/runtime.yaml`
  Default engineer manifest. Includes the engineer run-policy file plus shared domain files.
- `config/runtime.benchmark.yaml`
  Default benchmark manifest. Includes the benchmark run-policy file plus shared domain files.

### Run-policy fragments
- `config/run/engineer.yaml`
  Sets:
  - `run.spec_profile.interaction: interactive`
  - `run.spec_profile.rigor_level: L2`
  - `run.verification_profile: testbench-agent`
- `config/run/benchmark.yaml`
  Sets:
  - `run.spec_profile.interaction: non_interactive`
  - `run.spec_profile.rigor_level: L0`
  - `run.verification_profile: verilog-eval`

### Shared domain files
- `config/domains/agents.yaml`
  Worker pool sizes and all per-agent LLM settings.
- `config/domains/cli.yaml`
  CLI narration and output defaults.
- `config/domains/infrastructure.yaml`
  Broker settings and machine-specific tool path overrides.
- `config/domains/verification.yaml`
  Lint, simulation, and debug stage tuning.
- `config/domains/benchmark.yaml`
  Benchmark paths, flow defaults, prompt mode, sampling profiles, and benchmark-only operational knobs.

### Scenario manifests
These are thin overlays for specific internal workflows. They are not new config concepts, just named manifests with a small override on top of the shared files.

- `config/scenarios/wavefix_smoke.yaml`
  Benchmark manifest for the `wavefix_smoke` campaign.
- `config/scenarios/wavefix_smoke_live.yaml`
  Benchmark manifest for the `wavefix_smoke_live` campaign.
- `config/scenarios/wavefix_failed41.yaml`
  Benchmark manifest for the `wavefix_failed41` campaign.
- `config/scenarios/testspec_matrix.yaml`
  Test-oriented manifest that changes run policy and some pool/model settings for spec-matrix style runs.

Important interpretation:
- these extra `runtime.*.yaml` files are overlays, not extra config systems
- the architecture still has one shared config model
- most users only need `runtime.yaml` and `runtime.benchmark.yaml`

## High-Impact Public Sections
- `run`
  User-selected run policy.
- `agents`
  Worker pool sizing and per-role LLM settings.
- `cli`
  CLI narrative/output behavior.
- `infrastructure`
  Broker and local tool-path overrides.
- `verification`
  Lint/sim/debug tuning.
- `benchmark`
  Benchmark paths, flow controls, and sampling defaults.

## High-Impact Run Keys

### `run.spec_profile`
Two knobs only:

- `interaction`
  - `interactive`
  - `non_interactive`
- `rigor_level`
  - `L0`
  - `L1`
  - `L2`
  - `L3`
  - `L4`
  - `L5`

### `run.verification_profile`
One line, two values only:

- `testbench-agent`
  Engineer/CLI flow with generated TB path enabled.
- `verilog-eval`
  Benchmark verification mode.

## Typical Invocations

Engineer:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.yaml
```

Benchmark:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py doctor --config config/runtime.benchmark.yaml --benchmark
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign smoke
```

Scenario overlay:

```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/scenarios/wavefix_smoke.yaml --campaign wavefix_smoke
```

## Benchmark Defaults (Common)
- `benchmark.verilog_eval_root`: `third_party/verilog-eval`
- `benchmark.prompts_dir`: `third_party/verilog-eval/dataset_spec-to-rtl`
- `benchmark.output_root`: `artifacts/benchmarks/verilog_eval`
- `benchmark.oracle_manifest`: optional JSON mapping for custom `test_sv`/`ref_sv`
- `benchmark.flow_mode`: benchmark generation path selection
- `benchmark.prompt_mode`: raw prompt preservation policy for worker context
- `benchmark.disable_tb_generation`: skip generated TBs and rely on benchmark/public TB assets
- `benchmark.debug_rtl_only`: restrict benchmark debug edits to RTL only
- `benchmark.use_public_testbench`: bind benchmark-provided TB/reference assets into design context
- `benchmark.interface_equivalence`: interface match policy for generated RTL versus benchmark target
- `benchmark.rtl_language`: RTL language policy used in benchmark worker prompts/sanitization
- `benchmark.canonical`: default canonical sampling profile
- `benchmark.sampled`: default sampled profile
- `benchmark.sim_run_timeout_s`: simulation timeout used in benchmark-mode simulation worker
- `benchmark.near_miss_extra_retry_enabled`: allow near-miss simulation failures to receive extra debug retries
- `benchmark.near_miss_max_mismatches`: mismatch threshold for near-miss classification
- `benchmark.near_miss_extra_debug_retries`: extra retries granted for near-miss cases

## Practical Configuration Hygiene
1. Keep secrets in environment variables, not YAML.
2. Use `config/runtime.yaml` for normal engineer work.
3. Use `config/runtime.benchmark.yaml` for normal benchmark work.
4. Create new scenario manifests only when you need a named reproducible overlay.
5. Keep overlays thin; prefer overriding one or two values rather than copying the full config tree.

## Related Code
- `config/runtime.yaml`
- `config/runtime.benchmark.yaml`
- `core/runtime/config.py`
- `apps/cli/cli.py`
