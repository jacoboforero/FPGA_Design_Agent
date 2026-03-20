# Runtime Config Migration

Runtime behavior is YAML-driven, while secrets stay environment-driven.

## Ownership Rules
- YAML manifests: run policy, worker sizing, routing behavior, verification tuning, and benchmark defaults.
- Environment variables: provider credentials and secret tokens (for example `OPENAI_API_KEY`, `GROQ_API_KEY`, AgentOps keys).

## Typical Invocation
```bash
PYTHONPATH=. poetry run python3 apps/cli/cli.py --config config/runtime.yaml
PYTHONPATH=. poetry run python3 apps/cli/cli.py benchmark run --config config/runtime.benchmark.yaml --campaign smoke
```

## Practical Guidance
- Keep environment files focused on secrets.
- Keep non-secret behavior in YAML for reproducibility.
- Prefer manifest files over ad-hoc per-command overrides when running teams or CI.
- Normal engineer runs should use `config/runtime.yaml`.
- Normal benchmark runs should use `config/runtime.benchmark.yaml`.

## Related Code
- `core/runtime/config.py`
- `config/runtime.yaml`
- `config/runtime.benchmark.yaml`
- `apps/cli/cli.py`
