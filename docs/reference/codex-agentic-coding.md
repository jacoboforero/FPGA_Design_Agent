# Codex Agentic Coding Reference

Last checked against official OpenAI documentation on April 19, 2026.

## Official guidance adopted here

OpenAI's current Codex guidance is consistent on a few repo-management points:

- keep durable repo instructions in `AGENTS.md`, with nested overrides for specialized directories
- give Codex explicit task framing: goal, context, constraints, and done-when criteria
- plan first for larger or ambiguous tasks
- ask Codex to run relevant tests and review its own work before you accept a change
- use worktrees and repeatable setup for parallel or background work
- keep repo-shared Codex config in `.codex/config.toml` only when the setting is truly shared across contributors

## What was added to this repo

- a root [`AGENTS.md`](../../AGENTS.md) for repo-wide Codex instructions
- scoped overrides in [`adapters/`](../../adapters/AGENTS.override.md), [`agents/`](../../agents/AGENTS.override.md), [`workers/`](../../workers/AGENTS.override.md), [`prompts/`](../../prompts/AGENTS.override.md), and [`tests/`](../../tests/AGENTS.override.md)
- a shared planning format in [`PLANS.md`](../../PLANS.md)

These changes are workflow-only. They do not change the runtime architecture or application behavior.

## Why there is no committed `.codex/config.toml`

OpenAI recommends project-scoped Codex config for durable shared behavior, but this repo does not yet have an obvious shared default for model choice, approval policy, sandboxing, or worktree setup that should be forced on every contributor.

For this codebase, the highest-value shared artifacts are clear instructions and validation commands. Those now live in `AGENTS.md` and the scoped overrides. Individual contributors can still keep personal Codex defaults in `~/.codex/config.toml`.

## Recommended Codex workflow here

1. Start from the repo root so Codex can load `AGENTS.md` and any nested overrides in the area you are editing.
2. For cross-cutting work, follow the format in `PLANS.md` before editing.
3. Use the existing repo commands from `README.md` or `docs/cli.md` instead of inventing new entrypoints.
4. Validate with the narrowest affected tests first, then broader suites if the risk warrants them.
5. For parallel tasks in the Codex app, prefer Git worktrees so isolated changes do not interfere with your active checkout.

## Official sources

- OpenAI Developers, "Best practices": <https://developers.openai.com/codex/learn/best-practices>
- OpenAI Developers, "Custom instructions with AGENTS.md": <https://developers.openai.com/codex/guides/agents-md>
- OpenAI Developers, "Config basics": <https://developers.openai.com/codex/config-basic>
- OpenAI Developers, "Worktrees": <https://developers.openai.com/codex/app/worktrees>
- OpenAI Developers, "Local environments": <https://developers.openai.com/codex/app/local-environments>
- OpenAI Developers Cookbook, "Codex Prompting Guide": <https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide>
- OpenAI Developers Cookbook, "Using PLANS.md for multi-hour problem solving": <https://cookbook.openai.com/articles/codex_exec_plans/>
