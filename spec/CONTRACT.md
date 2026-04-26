# Contract

The harness contract is the runtime-neutral layer that Claude Code and Codex must both honor.

## State Files

Minimum state files:

- `tasks/index.json`
- `tasks/<task-dir>/index.json`
- `tasks/<task-dir>/phase<N>.md`
- `tasks/<task-dir>/phase<N>-output.json`
- `tasks/<task-dir>/docs-diff.md`
- `tasks/<task-dir>/role-<role-name>-output.json`
- `iterations/<iter-id>/requirement.md`
- `iterations/<iter-id>/check-report.json`
- `iterations/<iter-id>/role-<role-name>-output.json`

Every generated JSON state file should include `schema_version` once the first stable release is cut. Until then, scripts must tolerate missing `schema_version`.

## Task Index

`tasks/index.json` stores the list of tasks:

```json
{
  "tasks": [
    {
      "id": 1,
      "name": "example",
      "dir": "1-example",
      "status": "pending",
      "created_at": "2026-04-26T12:00:00+0900"
    }
  ]
}
```

Allowed task statuses:

- `pending`
- `completed`
- `error`

## Task Phase Index

`tasks/<task-dir>/index.json` stores the phase lifecycle:

```json
{
  "project": "target-project",
  "task": "example",
  "prompt": "original requirement text",
  "totalPhases": 2,
  "created_at": "2026-04-26T12:00:00+0900",
  "phases": [
    {
      "phase": 0,
      "name": "docs",
      "status": "pending"
    },
    {
      "phase": 1,
      "name": "implementation",
      "status": "pending"
    }
  ]
}
```

Allowed phase statuses:

- `pending`
- `completed`
- `error`

## Phase Lifecycle

The common lifecycle is:

1. Discover one requirement.
2. Build a document-backed implementation plan.
3. Create a task with phases.
4. Execute phases one by one.
5. Check the result.
6. Roll back if needed.

Phase rules:

- Phase 0 updates documentation.
- Each phase must be executable in an independent session.
- Acceptance criteria must be runnable commands.
- The phase runner must include phase file contents in the prompt, not only file paths.
- Phase result output is stored in `phase<N>-output.json`.
- Phase status is read from `tasks/<task-dir>/index.json` after execution.
- Phase 0 completion triggers `docs-diff.md` generation.

## Check Report

`iterations/<iter-id>/check-report.json` stores the post-build judgment:

```json
{
  "iter_id": "1-20260426_120000",
  "status": "pass",
  "task": {
    "dir": "tasks/1-example",
    "name": "example",
    "overall_status": "completed"
  },
  "phases": [],
  "issues": [],
  "conclusion": "",
  "carry_over": [],
  "progress": {
    "previous_iter_id": null,
    "signal": "no_prior_run",
    "summary": ""
  }
}
```

Allowed check statuses:

- `pass`
- `warn`
- `fail`

Allowed progress signals:

- `improved`
- `regressed`
- `inconclusive`
- `no_prior_run`

## Failure Categories

Headless failures must be categorized:

- `validation_failed`
- `sandbox_blocked`
- `context_insufficient`
- `runtime_error`

`context_insufficient` means the harness could not make a responsible decision without user input or missing repository context. It is not a generic runtime error.

`sandbox_blocked` means the runtime policy prevented a required action. In headless mode the provider must record this and return, not ask for approval.

## Headless Semantics

The canonical headless signal is:

```bash
AGENT_HEADLESS=1
```

Meaning:

- Do not ask questions.
- Do not wait for confirmation.
- Choose reasonable defaults only when the decision is supported by local context.
- If context is insufficient, record `context_insufficient` and stop.
- Do not depend on approval UI.

`AGENT_HEADLESS=1` means autonomous within known context, not unconditional progress.
