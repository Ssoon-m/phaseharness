# Phase: Clarify

Convert the user request into an execution contract.

Write `.phaseharness/runs/<run-id>/artifacts/01-clarify.md` with:

```markdown
# Phase 1: Clarify

## Original Request

## Clarification Questions

## User Decisions

## Goal

## Done When
- Concrete observable condition.

## Non-Goals

## Assumptions

## Open Questions
```

Rules:

- Ask concise grouped questions only when answers would materially change implementation.
- If the request is clear enough, ask no questions and record that no user question was required.
- Capture concrete user decisions so later phases do not depend on conversation memory.
- `Done When` must be specific enough for evaluate to decide pass, warn, or fail.
- Prefer the smallest useful increment when scope is broad.

