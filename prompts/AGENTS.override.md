# Prompts Override

- Most prompt families use a `meta.yaml`, `system.md`, and `user.md` triplet. Keep those files aligned when changing prompt behavior.
- Preserve placeholder names, expected sections, and fragment references unless you also update the calling code.
- Prefer reusing `prompts/fragments/` over duplicating shared rules across prompt families.
- Prompt edits can change behavior as much as code edits. Pair meaningful prompt changes with the closest tests and, when needed, doc updates.
- Typical validation:
- `pytest tests/core/test_prompt_registry.py -q`
- the closest agent, app, or execution tests that exercise the modified prompt family
