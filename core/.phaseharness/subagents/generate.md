# Phase: Generate

Execute only the current planned implementation phase file named in the continuation prompt.

Write or append `.phaseharness/runs/<run-id>/artifacts/04-generate.md` with:

```markdown
# Phase 4: Generate

## Phase <id>: <name>

### Status
completed | error

### Files Changed
- path: summary

### Validation
- command: result

### Notes
```

Rules:

- Read clarify, context, plan, and phase files before editing.
- Implement only the current implementation phase file from the continuation prompt.
- Run validation when possible.
- Do not reopen clarification or planning.
- Do not mark top-level `generate` as `completed`; the Stop hook does that when all implementation phases are complete.
- Mark the current implementation phase in `state.generate.phase_status` as `completed` or `error` before ending the turn.
- If using the state helper, run:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-generate-phase <phase-id> completed
```

- Use `context_insufficient`, `validation_failed`, `sandbox_blocked`, or `runtime_error` in `error_message` when failing.
