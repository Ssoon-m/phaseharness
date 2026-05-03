# Contract

The phaseharness contract is the runtime-neutral layer that Claude Code and
Codex must both honor.

## Activation Gate

The installed `Stop` hook is inert unless `.phaseharness/state/active.json`
contains:

```json
{
  "schema_version": 1,
  "active_run": "<run-id>",
  "activation_source": "phaseharness_skill",
  "status": "active"
}
```

Only the `phaseharness` skill may create this active state. The hook must not
start a run by interpreting an ordinary user prompt.

For session recovery, the skill may set:

```json
{
  "resume": {
    "status": "requested",
    "summary": "why the user asked to continue"
  }
}
```

The hook may bind a new provider session only after this explicit resume
request. A different `session_id` without a resume request must no-op.

## State Files

Minimum state files:

- `.phaseharness/state/active.json`
- `.phaseharness/state/index.json`
- `.phaseharness/runs/<run-id>/state.json`
- `.phaseharness/runs/<run-id>/artifacts/01-clarify.md`
- `.phaseharness/runs/<run-id>/artifacts/02-context.md`
- `.phaseharness/runs/<run-id>/artifacts/03-plan.md`
- `.phaseharness/runs/<run-id>/artifacts/04-generate.md`
- `.phaseharness/runs/<run-id>/artifacts/05-evaluate.md`
- `.phaseharness/runs/<run-id>/phases/phase-NNN.md`
- `.phaseharness/runs/<run-id>/outputs/stop-<turn>.json`

Allowed run statuses:

- `active`
- `waiting_user`
- `completed`
- `error`

Allowed phase statuses:

- `pending`
- `running`
- `waiting_user`
- `completed`
- `error`

Allowed evaluation statuses:

- `pending`
- `running`
- `pass`
- `warn`
- `fail`

## Run State

`.phaseharness/runs/<run-id>/state.json` stores workflow state:

```json
{
  "schema_version": 1,
  "run_id": "20260503-120000-example",
  "request": "original user request",
  "status": "active",
  "activation_source": "phaseharness_skill",
  "current_phase": "clarify",
  "phase_order": ["clarify", "context_gather", "plan", "generate", "evaluate"],
  "attempts": {
    "clarify": 1,
    "context_gather": 0,
    "plan": 0,
    "generate": 0,
    "evaluate": 0
  },
  "loop": {
    "current": 1,
    "max": 2
  },
  "max_attempts_per_phase": 2,
  "commit_mode": "none",
  "commits": {},
  "generate": {
    "queue": ["phase-001"],
    "current_phase": null,
    "phase_attempts": {},
    "phase_status": {
      "phase-001": "pending"
    },
    "completed_phases": [],
    "failed_phases": []
  },
  "needs_user": false,
  "session": {
    "provider": "codex",
    "session_id": "session-id",
    "turn_id": "turn-id",
    "transcript_path": ".tmp-transcript.jsonl",
    "model": "model",
    "updated_at": "2026-05-03T12:00:00+0900"
  },
  "session_history": [],
  "resume": {
    "status": "none",
    "summary": ""
  },
  "phases": {
    "clarify": {
      "status": "running",
      "artifact": "artifacts/01-clarify.md"
    }
  },
  "evaluation": {
    "status": "pending"
  }
}
```

## Hook Output

Continuation:

```json
{
  "decision": "block",
  "reason": "Continue the active phaseharness run..."
}
```

No-op:

- Claude Code: empty stdout and exit 0
- Codex: `{"continue":true}`

## Commit Result

Commit is optional. It is not a workflow phase.

`.phaseharness/bin/commit-result.py` may commit product changes for a completed
run whose evaluation is `pass` or `warn`. It excludes `.phaseharness/` state by
default unless `--include-harness-state` is supplied.
