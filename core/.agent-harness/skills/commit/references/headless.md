# Headless Commit Procedure

Use this reference when `AGENT_HEADLESS=1`.

Do not ask questions, wait for confirmation, or rely on interactive approval.
This procedure replaces the interactive flow.

## Rules

- Prefer no commit over a risky commit.
- If there are no product changes to commit, report that and exit
  successfully without creating an empty commit.
- Commit only paths selected by `scripts/commit-result.py`, paths explicitly
  listed by the caller, or paths that are clearly owned by the provided
  phaseloop phase context.
- If ownership is unclear, fail without committing.
- If staged changes already exist, fail and leave them untouched.
- Baseline-dirty paths are not automatically off limits in a phase-local commit.
  Commit them only when the provided phase context clearly owns those paths and
  the diff belongs to that phase. If ownership is unclear, leave them uncommitted.
- Push only when the caller explicitly requested push.

## Procedure

1. For a completed phaseloop task result, follow `phaseloop-result.md`.
2. For a phaseloop phase-local commit, do not call `scripts/commit-result.py`.
   Inspect the phase file, task index, git status, and git diff. Stage only
   product paths that clearly belong to that phase, even when those paths were
   already dirty at task start. Do not commit `tasks/` runtime state unless the
   phase explicitly asks for phaseloop state to be product history. If ownership
   is unclear, stop without committing.
3. If the caller provided explicit paths and a commit message, stage only those
   paths and commit with that message.
4. If neither path is deterministic, stop without committing and report why.
5. If push was explicitly requested, push after the commit succeeds.
