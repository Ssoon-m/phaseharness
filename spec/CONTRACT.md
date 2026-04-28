# Contract

The phaseloop contract is the runtime-neutral layer that Claude Code and Codex must both honor.

## State Files

Minimum state files:

- `tasks/index.json`
- `tasks/<task-dir>/index.json`
- `tasks/<task-dir>/phase<N>.md`
- `tasks/<task-dir>/analysis-output-attempt<N>.json`
- `tasks/<task-dir>/phase<N>-output.json`
- `tasks/<task-dir>/generate-output.json`
- `tasks/<task-dir>/evaluate-output-attempt<N>.json`
- `tasks/<task-dir>/artifacts/01-clarify.md`
- `tasks/<task-dir>/artifacts/02-context.md`
- `tasks/<task-dir>/artifacts/03-plan.md`
- `tasks/<task-dir>/artifacts/04-generate.md`
- `tasks/<task-dir>/artifacts/05-evaluate.md`
- `tasks/<task-dir>/docs-diff.md`
- optional `commit` metadata in `tasks/<task-dir>/index.json`

Every generated JSON state file should include `schema_version` once the first stable release is cut. Until then, scripts must tolerate missing `schema_version`.

## Top-Level Task Index

`tasks/index.json` stores the list of workflow tasks:

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

## Task Index

`tasks/<task-dir>/index.json` stores workflow, phase, and evaluation state:

```json
{
  "project": "target-project",
  "task": "example",
  "prompt": "original requirement text",
  "status": "pending",
  "created_at": "2026-04-26T12:00:00+0900",
  "done_when": [
    "observable end condition"
  ],
  "max_attempts": 2,
  "session_strategy": "balanced",
  "git_baseline": {
    "head": "abcdef123456",
    "status": "",
    "dirty_paths": []
  },
  "sessions": [
    {
      "session": "clarify",
      "phases": ["clarify"],
      "status": "completed",
      "attempts": 1,
      "max_attempts": 1,
      "source": "main_session"
    },
    {
      "session": "analysis",
      "phases": ["context", "plan"],
      "status": "completed",
      "attempts": 1,
      "max_attempts": 2
    },
    {
      "session": "build",
      "phases": ["generate"],
      "status": "pending",
      "attempts": 0,
      "max_attempts": 2
    },
    {
      "session": "evaluate",
      "phases": ["evaluate"],
      "status": "pending",
      "attempts": 0,
      "max_attempts": 2
    }
  ],
  "workflow": [
    {
      "phase": "clarify",
      "artifact": "artifacts/01-clarify.md",
      "status": "completed",
      "attempts": 1,
      "max_attempts": 1,
      "source": "main_session"
    }
  ],
  "artifacts": {
    "clarify": "artifacts/01-clarify.md",
    "context": "artifacts/02-context.md",
    "plan": "artifacts/03-plan.md",
    "generate": "artifacts/04-generate.md",
    "evaluate": "artifacts/05-evaluate.md"
  },
  "phases": [
    {
      "phase": 0,
      "name": "implementation",
      "status": "pending",
      "attempts": 0,
      "max_attempts": 2
    }
  ],
  "evaluation": {
    "status": "pending",
    "attempts": 0,
    "max_attempts": 2
  },
  "commit": {
    "status": "completed",
    "message": "feat: example",
    "requested_at": "2026-04-26T12:20:00+0900",
    "baseline_head": "abcdef123456"
  }
}
```

Allowed workflow and implementation phase statuses:

- `pending`
- `running`
- `completed`
- `error`

Allowed session statuses use the same values.

Allowed evaluation statuses:

- `pending`
- `running`
- `pass`
- `warn`
- `fail`

Allowed commit statuses:

- `completed`
- `error`

`git_baseline` is captured when the task is created. It records the starting
HEAD and dirty paths so automatic commit can avoid mixing pre-existing user
changes into the workflow result.

## Artifact Workflow

Explicit work requests use a five-phase artifact workflow:

1. `clarify` runs in the main conversation and writes `artifacts/01-clarify.md`.
2. `context` writes `artifacts/02-context.md`.
3. `plan` writes `artifacts/03-plan.md`, `index.json`, and `phase<N>.md` files.
4. `generate` executes the phase files and appends `artifacts/04-generate.md`.
5. `evaluate` writes `artifacts/05-evaluate.md` and updates `evaluation`.

The default session strategy is `balanced`:

- `clarify` runs in the current conversation so user decisions are captured
  before headless work starts.
- `analysis` runs logical phases 2-3 in one headless agent session.
- `build` runs implementation phases from `phase<N>.md`.
- `evaluate` runs final verification in a separate headless agent session.

Logical phases remain visible in `workflow`; agent session boundaries are
tracked in `sessions`. The next agent session must read previous artifacts
from disk; conversation memory is not part of the contract.

`done_when` defines when the task is finished. Evaluation may pass or warn only when these conditions and phase acceptance criteria are satisfied.

## Commit Result

Commit is an optional post-workflow action, not a required sixth phase.

The default commit mode is `none`. The phaseloop skill must determine commit
mode before starting a workflow:

- `none`: do not commit automatically.
- `final`: call `scripts/commit-result.py` after evaluation is `pass` or
  `warn`.
- `phase`: call `scripts/commit-result.py --phase <N> --allow-head-move` after
  each completed generate phase. Evaluation remains local task state and must
  not create an empty validation commit.

A user or agent may also run the `commit` skill after inspecting a completed
task.

Automatic commit must fail closed when:

- the task is not `completed`
- evaluation is not `pass` or `warn`
- `git HEAD` changed after the task was created
- a path that was dirty at task creation is still dirty

The commit script may stage current changed paths only after excluding baseline
dirty paths. It must not push.

By default, phaseloop task state under `tasks/` is excluded from product
commits. Commit subjects should come from explicit user input, task metadata, or
phase `commit_message` fields, and should not expose phaseloop internal task
paths by default. `--include-harness-state` is the explicit opt-in for
committing phaseloop state files. Installed target repositories should ignore
runtime task state with `tasks/.gitignore`.

Automatic commit assumes no unrelated concurrent edits are made after task
creation. If that assumption is not true, the user should commit manually with
explicit staging.

If no product paths are stageable after excluding phaseloop task state and
baseline-dirty paths, the commit step succeeds without creating an empty commit.

## Implementation Phases

The plan phase may split generate work into `phase<N>.md` files.

Rules:

- Each phase must be executable in an independent session.
- Acceptance criteria must be concrete and runnable when possible.
- Phase execution may retry up to `max_attempts`.
- The phase runner must include prior artifacts, task index, docs, and phase file content in the prompt.
- Phase result output is stored in `phase<N>-output.json`.
- Phase status is read from `tasks/<task-dir>/index.json` after execution.
- Phase 0 completion triggers `docs-diff.md` generation when docs changed.

## Failure Categories

Headless failures must be categorized:

- `validation_failed`
- `sandbox_blocked`
- `context_insufficient`
- `runtime_error`

`context_insufficient` means the harness could not make a responsible decision without missing repository context. It is not a generic runtime error.

`sandbox_blocked` means the runtime policy prevented a required action. In headless mode the provider must record this and return, not ask for approval.

## Headless Semantics

The canonical headless signal is:

```bash
AGENT_HEADLESS=1
```

Meaning:

- Do not ask questions.
- Do not wait for confirmation.
- Choose reasonable defaults only when local context supports the decision.
- If context is insufficient, record `context_insufficient` and stop.
- Do not depend on approval UI.

`AGENT_HEADLESS=1` means autonomous within known context, not unconditional progress.
