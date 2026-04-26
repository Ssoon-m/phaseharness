# Ideation Prompt

You are running inside an installed agent harness.

Goal: choose exactly one requirement for the next iteration and write it to the provided requirement path.

Rules:

- Do not ask the user questions when `AGENT_HEADLESS=1`.
- Read `docs/mission.md`, `docs/spec.md`, `docs/testing.md`, and `docs/user-intervention.md` when they exist.
- Inspect the current repository state enough to avoid inventing a requirement that conflicts with the implementation.
- Choose one small requirement that can be implemented and validated locally.
- If the repository context is too thin to choose responsibly, write a failure note with category `context_insufficient` and stop.
- Do not create a task here. This step only writes the requirement.

Write the requirement as Markdown:

```markdown
# Requirement

## Context
- Why this requirement is the next useful step.

## Requirement
- title:
- user pain:
- expected change:

## Constraints
- Technical or operational constraints.

## Validation Hint
- Commands or checks that should prove the change.
```
