# Documentation Goals

This document defines what "good documentation" means for this codebase.

The main purpose is to keep documentation focused on user outcomes: helping people use the system correctly, quickly, and confidently.

## Primary Goal
Documentation should reduce time-to-value.

A reader should be able to go from "I have this design or evaluation task" to "I completed it successfully" without confusion, guesswork, or unnecessary back-and-forth.

## User Goals

### 1. Support the two primary user groups clearly
Our docs must explicitly serve both:
- hardware engineers using the design CLI flow to build real design artifacts;
- researchers using the benchmark flow to evaluate model/system behavior.

This matters because these users have different definitions of success, different workflows, and different questions.

### 2. Make each user path obvious
The docs should make it clear where each user starts and where they go next.

Expected paths:
- Engineer path: spec refinement -> planning -> execution -> artifact review.
- Research path: benchmark setup -> scripted runs -> result comparison.

If a user cannot identify their path quickly, documentation is failing.

### 3. Emphasize action over description
Documentation should not only explain what the system is, but enable users to do useful work.

Core workflows should be runnable from the docs with concrete commands and clear expected outputs.

## Quality Goals

### 4. High task success rate
A reader should be able to complete core workflows from docs alone.

If users routinely need to ask "what now?" after following steps, the docs need improvement.

### 5. Fast time-to-first-success
A new user should be able to get a first successful run in a reasonable amount of time for their role.

Good docs remove setup ambiguity and minimize dead ends.

### 6. Reliable copy-paste commands
Commands in docs should work as written in the expected environment.

Broken or outdated commands erode trust immediately.

### 7. Tight code-doc alignment
Documentation must match current behavior in code:
- state names,
- CLI flags,
- workflow stages,
- artifact paths,
- output expectations.

Stale docs are often worse than missing docs because they cause incorrect actions with high confidence.

### 8. Clear role separation
Engineer-oriented guidance and researcher-oriented guidance should be explicitly separated in structure and wording.

Blending both in a single undifferentiated path increases cognitive load and causes the wrong assumptions.

### 9. Strong navigation quality
From the docs index, users should be able to find the correct page quickly (typically within one or two clicks).

A well-structured map is part of documentation quality, not an optional extra.

### 10. Full critical workflow coverage
Documentation should cover the high-impact lifecycle:
- setup and prerequisites,
- normal run paths,
- failure and recovery paths,
- benchmark execution and interpretation.

Coverage gaps in these areas are high-cost for users.

### 11. Practical troubleshooting value
Frequent failure modes should have direct, actionable fixes.

Troubleshooting guidance should prioritize diagnosis and next action, not generic advice.

### 12. Maintainability and trust
Docs should be written so they can stay current:
- organized around stable user goals,
- explicit about where behavior comes from,
- easy to update when code changes.

High-impact claims should be grounded in source-of-truth references in the repo.

## Style Goals

### 13. Human-first clarity
Write in plain language with direct, practical framing.

User-facing pages should optimize for understanding and action, not internal implementation detail.

### 14. Right detail in the right place
High-level pages should guide decisions and workflows.
Deep technical details should live in component/reference pages.

This separation keeps docs usable for both onboarding and deep debugging.

### 15. Realistic examples
Examples and commands should reflect actual current behavior and current CLI interface.

Documentation quality includes realism: examples should feel trustworthy because they are accurate and current.

## Documentation Maintenance Checklist
Use this checklist for any runtime/CLI change that can affect user-facing behavior.

### Required updates on behavior changes
- Update command examples in user-facing runbooks (`interactive-run`, `benchmark-run`, `cli`).
- Update reference docs for changed config keys or defaults (`runtime-config`).
- Update troubleshooting sections when new failure signatures appear.
- Update glossary terms if new concepts are introduced.
- Update tests/docs command references if new validation commands are required.

### Required verification before considering docs "done"
- Run `python3 scripts/validate_docs.py` and confirm link checks pass.
- Run `python3 scripts/validate_docs.py --run-commands` when environment dependencies are available.
- Confirm critical commands in docs are copy-paste runnable in the expected environment.
- Confirm high-impact pages include a concrete "last verified" date.

### Review quality gates
- Role clarity: engineer and researcher paths remain explicit and easy to follow.
- Workflow completeness: setup, run, verify, troubleshoot, and next steps all present.
- Evidence quality: examples and claims map to current implementation behavior.
- Navigation quality: users can reach the right page in one to two hops from docs index.
