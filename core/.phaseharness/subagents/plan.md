# Phase: Plan

Convert the clarify contract and gathered context into an ordered Ralph-style implementation phase queue with acceptance criteria.

Write `.phaseharness/runs/<run-id>/artifacts/03-plan.md` and one or more files under `.phaseharness/runs/<run-id>/phases/`.

`artifacts/03-plan.md` should include:

```markdown
# Phase 3: Plan

## Implementation Phases

## Acceptance Criteria

## Validation Plan

## Commit Guidance
```

Each `phases/phase-NNN.md` file should include:

- concrete work
- files in scope
- acceptance criteria
- validation commands where possible
- expected state update when complete
- optional commit message

Also update `state.json`:

```json
{
  "generate": {
    "queue": ["phase-001"],
    "phase_status": {
      "phase-001": "pending"
    }
  }
}
```

Rules:

- Do not implement code.
- Do not overwrite clarify or context artifacts.
- Keep phases small enough for isolated execution.
- Dependencies and done conditions must be explicit.
- Use stable ids such as `phase-001`, `phase-002`, and `phase-003`.
- The Stop hook will consume these implementation phase files one at a time during `generate`.
