# Phase: Clarify

Convert the user request into an execution contract.

Write `.phaseharness/runs/<run-id>/artifacts/01-clarify.md` with:

```markdown
# Phase 1: Clarify

## Executor
- requested_subagent:
- execution_mode:
- delegation_error:

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

- Read any existing `01-clarify.md` before rewriting it.
- If this phase is resuming after `waiting_user`, treat the resume summary and
  latest user response as answers to the existing clarification questions.
- When user responses resolve the material blockers, update `User Decisions`,
  remove resolved items from `Open Questions`, write the completed execution
  contract, and set `clarify` to `completed`.
- If user responses are incomplete, preserve the decisions already made, ask
  only the remaining blocking questions, set `clarify` back to `waiting_user`,
  and stop.
- Ask concise grouped questions only when answers would materially change implementation.
- If the request is clear enough, ask no questions and record that no user question was required.
- Capture concrete user decisions so later phases do not depend on conversation memory.
- `Done When` must be specific enough for evaluate to decide pass, warn, or fail.
- Prefer the smallest useful increment when scope is broad.
