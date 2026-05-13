---
name: context-gather
description: Use when the user explicitly invokes context-gather, or when a phaseharness continuation asks for the context_gather stage. Collects repository facts, relevant files, patterns, constraints, risks, docs, and validation commands without product code edits.
---

# Context Gather

Context gather records repository facts needed for planning. It does not implement or refactor product code.

## Run State

- Use the continuation run id when provided.
- If `context-gather` is run directly without a run id, create a manual run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode manual --stage context-gather --request "<request>" --commit-mode none --json
```

- Manual runs stop after this stage. Do not call `next`.

## Rules

- Inspect repository structure, relevant files, docs, conventions, constraints, risks, and validation commands.
- Prefer `rg`, `rg --files`, and focused file reads.
- Do not modify product code.
- Do not paste full source files into the artifact.
- If clarify was skipped, document why the requirement is clear enough to gather context.
- Include file paths and the reason each path matters.

## Configured Context

Before broad repository inspection, run:

```bash
python3 .phaseharness/skills/context-gather/scripts/render-context-config.py
```

Use the rendered output as the rendered context config.

Document lines use `source` `(kind, priority, status)`: description. Status describes path/glob availability, not task relevance.

For every configured document in the rendered context config, record exactly one outcome:

- If the document is read and affects this task, record it under `Referenced Documents`.
- If the document exists but does not affect this task, record it under `Skipped Context`.
- If the document is unavailable (`missing`, `no_matches`, `not_a_file`, `unreadable`, or `invalid`), record it under `Risks`.

`required` means the document must be checked for relevance. It does not force the document into `Referenced Documents`.

Gather only context that can affect the requested implementation: target files, architecture boundaries, API/data/component contracts, coding conventions, validation commands, or risks that could change the plan.

Do not summarize unrelated project-wide documentation. If a configured document is broad, extract only the parts that constrain this task.

## Artifact

Write `.phaseharness/runs/<run-id>/artifacts/context.md`:

```markdown
# Context Gather

## Project Shape

## Relevant Files

- path: reason

## Referenced Documents

- path:
- reason:
- applied_rules:
- planning_implication:

## Skipped Context

- source:
- reason:

## Existing Patterns

## Constraints

## Risks

## Validation Commands

## Recommended Next Step
```

When complete:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage context-gather completed --run-id <run-id>
```
