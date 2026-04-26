---
name: ideation
description: Choose one grounded requirement for the next harness iteration.
---

# Ideation

Use this skill to choose one small, local, document-backed requirement.

Read the project docs and current implementation before choosing. Prefer requirements that are:

- useful to the target project
- small enough for one task
- verifiable with local commands
- not blocked by deployment, billing, credentials, or external approval

When `AGENT_HEADLESS=1`, do not ask questions. If the decision cannot be made responsibly, write a `context_insufficient` result instead of guessing.
