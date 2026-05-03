# Phase: Evaluate

Verify that generated work satisfies the clarify `Done When` contract and planned acceptance criteria.

Write `.phaseharness/runs/<run-id>/artifacts/05-evaluate.md` with:

```markdown
# Phase 5: Evaluate

## Result
pass | warn | fail

## Checks Run
| Command | Result | Notes |
|---|---|---|

## Done Conditions
| Condition | Status | Evidence |
|---|---|---|

## Issues Fixed

## Remaining Issues

## Recommendation
```

Also update `state.json`:

```json
{
  "evaluation": {
    "status": "pass",
    "attempts": 1,
    "completed_at": "<ISO timestamp>"
  }
}
```

Rules:

- Run available checks when possible.
- Fix validation errors only when the fix is local and clearly in scope.
- Use `warn` for incomplete confidence and `fail` for unmet done conditions.
- If the result is `fail` and the issue is fixable within the remaining loop budget, create one or more follow-up implementation phase files under `.phaseharness/runs/<run-id>/phases/` using the next `phase-NNN.md` id, and add them to `state.generate.queue` with `pending` status.
- If the result is `fail` because requirements are unclear, set the run to `waiting_user` instead of adding speculative follow-up phases.
- The Stop hook will return to `generate` only when `loop.current < loop.max` and pending follow-up implementation phases exist.
