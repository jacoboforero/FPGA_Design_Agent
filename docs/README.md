# Documentation Index

This folder explains how the pipeline works today: what users run, what each runtime component does, and where to look when something fails.

CLI examples in this docs set assume one of these environments:
- inside the `app` container after `make build`, `make up`, `make deps`, `make shell`
- on the host after `poetry install --with dev`

When examples use `PYTHONPATH=. poetry run python3 ...`, use that exact form unless a page explicitly says otherwise.

## Start Here
- [vision-and-ux.md](./vision-and-ux.md): goals, product intent, and intended user experience.
- [overview.md](./overview.md): end-to-end lifecycle in plain language.
- [cli.md](./cli.md): command surface and decision matrix.
- [project-brief.md](./project-brief.md): one-page AI-for-EDA project brief for external technical reviewers.
- [../examples/counter3](../examples/counter3): compact checked-in example artifacts.

## Quick Start by Role
### If you are a hardware engineer
Start here:
1. [cli.md](./cli.md)
2. [workflows/interactive-run.md](./workflows/interactive-run.md)
3. [spec-and-planning.md](./spec-and-planning.md)
4. [workflows/failure-repair-loop.md](./workflows/failure-repair-loop.md)

### If you are a researcher
Start here:
1. [workflows/benchmark-run.md](./workflows/benchmark-run.md)
2. [workflows/benchmark-campaigns.md](./workflows/benchmark-campaigns.md)
3. [benchmark-methodology.md](./benchmark-methodology.md)
4. [benchmark-optimization-log-20260429.md](./benchmark-optimization-log-20260429.md)
5. [observability.md](./observability.md)
6. [workflows/artifact-hygiene.md](./workflows/artifact-hygiene.md)

## System Design
- [architecture.md](./architecture.md): runtime components, state machine, and execution flow.
- [agents.md](./agents.md): what each LLM-backed agent does.
- [queues-and-workers.md](./queues-and-workers.md): queue routing and deterministic worker behavior.
- [spec-and-planning.md](./spec-and-planning.md): how L1-L5 specs are frozen and handed off.
- [schemas.md](./schemas.md): message contracts and enums.

## Operations
- [workflows/interactive-run.md](./workflows/interactive-run.md): engineer runbook with execution checkpoints and troubleshooting.
- [workflows/failure-repair-loop.md](./workflows/failure-repair-loop.md): retry and repair behavior.
- [workflows/benchmark-run.md](./workflows/benchmark-run.md): VerilogEval v2 benchmark runbook.
- [workflows/benchmark-campaigns.md](./workflows/benchmark-campaigns.md): benchmark campaign YAML authoring and execution.
- [benchmark-methodology.md](./benchmark-methodology.md): benchmark interpretation and comparison guidance.
- [benchmark-optimization-log-20260429.md](./benchmark-optimization-log-20260429.md): GPT-4o/GPT-4.1 VerilogEval-v2 optimization results and comparison notes.
- [observability.md](./observability.md): where run telemetry and cost logs go.
- [workflows/artifact-hygiene.md](./workflows/artifact-hygiene.md): indexing and organizing historical artifacts.
- [case-studies/example-run.md](./case-studies/example-run.md): concrete spec-to-RTL walkthrough.
- [demo-script.md](./demo-script.md): two-minute demo outline for project walkthroughs.

## Reference
- [reference/runtime-config.md](./reference/runtime-config.md): high-impact runtime config keys.
- [reference/codex-agentic-coding.md](./reference/codex-agentic-coding.md): how this repo is structured for Codex and other agentic workflows.
- [reference/test-commands.md](./reference/test-commands.md): quick test command list.
- [test-plan.md](./test-plan.md): test strategy and suite coverage.
- [config-migration.md](./config-migration.md): YAML vs environment ownership.
- [glossary.md](./glossary.md): shared terminology used across docs.

## Component Notes
- [components/orchestrator.md](./components/orchestrator.md)
- [components/workers.md](./components/workers.md)
- [components/llm-gateway.md](./components/llm-gateway.md)
- [components/ui-bridge.md](./components/ui-bridge.md)
