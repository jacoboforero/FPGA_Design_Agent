# Documentation guide

Start here to get oriented, then drill into the file you need.

- **overview.md** — high-level flow (plan → execute → decide)
- **architecture.md** — components, queues, state machine
- **agents.md** — role-by-role inputs/outputs
- **cli.md** — commands and run examples
- **spec-and-planning.md** — L1–L5 checklist and planner handoff
- **queues-and-workers.md** — RabbitMQ layout, DLQ expectations
- **schemas.md** — contract pointers (see `core/schemas/` for source)
- **test-plan.md** — what to exercise by default vs optional jobs

Common paths:
- Locked specs: `artifacts/task_memory/specs/`
- Planner outputs: `artifacts/generated/{design_context.json, dag.json}`
- Generated RTL/TB: `artifacts/generated/rtl/`
- Logs/artifact pointers: `artifacts/task_memory/<node>/<stage>/`
