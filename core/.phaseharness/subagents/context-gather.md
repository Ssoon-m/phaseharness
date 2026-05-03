# Phase: Context Gather

Read the clarify artifact as the fixed task contract. Gather only repository facts needed for planning and implementation.

Write `.phaseharness/runs/<run-id>/artifacts/02-context.md` with:

```markdown
# Phase 2: Context Gather

## Executor
- requested_subagent:
- execution_mode:
- delegation_error:

## Project Shape

## Tech Stack

## Relevant Files
- path: why it matters

## Existing Patterns

## Constraints

## Risks

## Validation Commands
```

Rules:

- Do not implement code.
- Prefer concrete file paths over broad summaries.
- Keep discovery bounded to the clarified task.
- If context is insufficient, state exactly what is missing and mark the phase `error` or `waiting_user` in state.
