# Runtime Config Migration

Runtime behavior is YAML-driven, while secrets stay environment-driven.

## Ownership Rules
- YAML (`config/runtime.yaml`): presets, worker sizing, routing behavior, retry policy, benchmark defaults.
- Environment variables: provider credentials and secret tokens (for example `OPENAI_API_KEY`, `GROQ_API_KEY`, AgentOps keys).

## Typical Invocation
```bash
PYTHONPATH=. python3 apps/cli/cli.py --config config/runtime.yaml --preset engineer_fast
PYTHONPATH=. python3 apps/cli/cli.py benchmark run --config config/runtime.yaml --preset benchmark --campaign smoke
```

## Practical Guidance
- Keep environment files focused on secrets.
- Keep non-secret behavior in YAML for reproducibility.
- Prefer presets over ad-hoc per-command overrides when running teams or CI.

## Related Code
- `core/runtime/config.py`
- `config/runtime.yaml`
- `apps/cli/cli.py`
