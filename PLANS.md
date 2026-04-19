# PLANS.md

Use this format for work that is cross-cutting, ambiguous, or likely to take multiple iterations. Short, single-file fixes usually do not need it.

## When to use a plan

- the change touches multiple packages or runtime stages
- behavior must remain stable while implementation details move
- the task needs staged validation
- open questions could change the implementation path

## Suggested template

### Goal

State the user-visible outcome in one or two sentences.

### Constraints

List the boundaries that cannot move, such as architecture, interfaces, rollout constraints, or safety requirements.

### Relevant context

Point to the files, docs, configs, and tests that define the current behavior.

### Plan

1. Inspect the smallest set of files needed to confirm the current behavior.
2. Make the narrowest change that satisfies the goal.
3. Validate with focused tests first, then broader checks only if the risk warrants them.
4. Update docs or prompts only when they are part of the behavior or workflow change.

### Validation

- exact commands to run
- what result counts as success
- what still needs manual review

### Risks and rollback

- likely failure modes
- what to revert or inspect first if validation fails

### Status log

- capture major discoveries, scope changes, and validation results as the work progresses
