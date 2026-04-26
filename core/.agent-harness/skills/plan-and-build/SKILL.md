---
name: plan-and-build
description: Turn one requirement into docs, task phases, implementation, and validation.
---

# Plan And Build

Use this skill after a requirement has been selected.

Required sequence:

1. Read docs and repository state.
2. Produce a small implementation plan.
3. Run the `tech-critic-lead` role if available.
4. Create a task using the task creation contract.
5. Execute phases with `scripts/run-phases.py`.
6. Leave state in `tasks/` and `iterations/`.

When `AGENT_HEADLESS=1`, do not ask questions. Record `context_insufficient` if local context is not enough.
