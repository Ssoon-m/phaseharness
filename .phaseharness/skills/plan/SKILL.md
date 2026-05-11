---
name: plan
description: Use when the user explicitly invokes plan, or when a phaseharness continuation asks for the plan stage. Creates a planning artifact and self-contained phase files without implementation.
---

# Plan

Plan creates executable phase files for later `generate` runs. It does not implement.

## Run State

- Use the continuation run id when provided.
- If `plan` is run directly without a run id, create a manual run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode manual --stage plan --request "<request>" --commit-mode none --json
```

- Manual runs stop after this stage. Do not call `next`.

## Inputs

Read available artifacts from `.phaseharness/runs/<run-id>/artifacts/`, especially:

- `clarify.md`
- `context.md`

If an input is missing, either proceed only when the request is still concrete enough, or mark the stage `waiting_user` with the missing decision.

## Rules

- Do not modify product code.
- Prioritize independent implementation and verification over minimizing phase count.
- Each phase must be executable by a fresh implementer without conversation memory.
- Each phase must be reviewable by a fresh reviewer.
- Specify target files, allowed changes, forbidden changes, acceptance criteria, and validation commands.

## Phase Splitting Guidelines

Split phases so each one can be implemented and reviewed independently.

Good reasons to create a separate phase:

- A user-visible feature or behavior can be completed and validated on its own.
- The work is likely to take a long time or touch many files.
- The work has a distinct risk profile, such as data migration, state handling, UI behavior, external integration, or test infrastructure.
- Different phases have different validation commands or acceptance criteria.
- One phase can reduce uncertainty for later phases, such as adding a parser, adapter, or test harness before broader behavior changes.
- File ownership or allowed changes would otherwise become too broad for a fresh implementer to follow safely.

Avoid phase splits that are only mechanical:

- Do not split by file when no file-level change is independently useful or reviewable.
- Do not create phases that require hidden conversation memory from previous phases.
- Do not create phases that leave the repository in an incoherent or untestable state unless the phase explicitly documents that limitation and why it is unavoidable.

Each phase should state:

- the feature or behavior slice it owns
- the exact target files or directories
- what must not be changed
- how a reviewer can verify the phase without reading chat history
- whether later phases depend on it

## Outputs

Write `.phaseharness/runs/<run-id>/artifacts/plan.md` with the phase breakdown and rationale.

Create one or more phase files under `.phaseharness/runs/<run-id>/phases/` using `phase-001.md`, `phase-002.md`, and so on.

```markdown
# Phase NNN: <title>

## Goal

## Phase Boundary

- why this is a separate phase:
- independent validation:

## Inputs

- run:
- clarify artifact:
- context artifact:
- plan artifact:

## Dependencies

- required previous phases:
- later phases unlocked by this phase:

## Target Files

- path: reason

## Allowed Changes

## Forbidden Changes

## Implementation Notes

## Acceptance Criteria

- [ ]

## Validation Commands

- command:
- expected:

## State Update

- On success:
- On failure:
```

When complete:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage plan completed --run-id <run-id>
```
