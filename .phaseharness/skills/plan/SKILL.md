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

If an input is missing, proceed with explicit assumptions when possible and record the missing decision as a risk.

Use `context.md` as factual input only. Ignore any context-gather wording that recommends phase count, phase names, split decisions, merge decisions, or implementation batching.

## Rules

- Do not modify product code.
- Prioritize independent implementation and verification over minimizing phase count.
- Each phase must be executable by a fresh implementer without conversation memory.
- Each phase must be reviewable by a fresh reviewer.
- Specify target files, allowed changes, forbidden changes, acceptance criteria, validation commands, and stop conditions.
- Include relevant local patterns or contracts the worker should preserve.
- Do not write complete code in the plan. Capture boundaries, constraints, and verification.

## Phase Splitting Guidelines

Split phases so each one can be implemented and reviewed independently with the smallest practical context.

Use failure boundary, validation boundary, and context size as supporting split criteria. Do not split by file alone.

Before writing phase files, list candidate functional responsibilities from the request and factual context in `context.md`, then decide whether each candidate should be its own phase or merged into another phase.

Default to splitting when a candidate has its own failure mode, externally observable behavior, contract, state model, validation concerns, target file ownership, long implementation time, or broad context needs.

Functional responsibility is the primary boundary:

- Split phases when responsibilities are different.
- Do not merge responsibilities just because they are connected in one workflow or can be checked together in final `evaluate`.
- Each phase should be verifiable within its own responsibility while keeping the repository coherent; full workflow verification belongs in `evaluate`.

Good reasons to create a separate phase:

- An externally observable feature or behavior can be completed and validated on its own.
- The work is likely to take a long time or touch many files.
- The work has a distinct risk profile, such as data migration, state handling, external integration, hardware/runtime behavior, or test infrastructure.
- Different phases have different validation commands or acceptance criteria.
- One phase can reduce uncertainty for later phases, such as adding a parser, adapter, or test harness before broader behavior changes.
- File ownership or allowed changes would otherwise become too broad for a fresh implementer to follow safely.
- A contract change, such as a type, API, schema, prop, or data shape, must be reviewed before downstream behavior changes.

Split before writing phase files if:

- one phase would cover multiple independent functional responsibilities
- one phase would cover multiple independent contracts, state models, or failure boundaries
- one phase would require broad context from unrelated parts of the repository
- one phase would likely take a long time to implement or review
- one phase mixes changes with different failure modes
- one phase mixes changes with different validation methods
- one phase changes shared/common behavior and responsibility-specific behavior together
- one phase has a broad target file set that makes failure attribution difficult
- one phase requires multiple independent design decisions or assumptions

Avoid phase splits that are only mechanical:

- Do not split by file when no file-level change is independently useful or reviewable.
- Do not split implementation and tests into separate phases when the behavior can be tested in the same phase.
- Do not create phases that require hidden conversation memory from previous phases.
- Do not create phases that leave the repository in an incoherent or untestable state unless the phase explicitly documents that limitation and why it is unavoidable.

Each phase should state:

- the functional responsibility it owns
- the exact target files or directories
- what must not be changed
- how a reviewer can verify the phase without reading chat history
- whether later phases depend on it
- exact validation commands and expected outcomes
- stop conditions when the worker should return `error` instead of guessing

Merge candidates only when they are the same kind of functional work and can be implemented, reviewed, and verified as one responsibility. Explain non-obvious merges in `artifacts/plan.md`.

## Outputs

Write `.phaseharness/runs/<run-id>/artifacts/plan.md` with the phase breakdown, rationale, dependency order, and validation strategy.

Include a short `Phase Split Review` in `artifacts/plan.md` explaining the selected phase boundaries and any non-obvious merges.

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
- relevant local patterns or contracts:
- suggested order:

## Acceptance Criteria

- [ ]

## Validation Commands

- command:
- expected:

## Stop Conditions

- return `error` instead of guessing if:

## State Update

- On success:
- On failure:
```

When complete:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage plan completed --run-id <run-id>
```
