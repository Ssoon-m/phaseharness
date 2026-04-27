# Headless Commit Procedure

Use this reference when `AGENT_HEADLESS=1`.

Do not ask questions, wait for confirmation, or rely on interactive approval.
This procedure replaces the interactive flow.

## Rules

- Prefer no commit over a risky commit.
- Commit only paths selected by `scripts/commit-result.py`, paths explicitly
  listed by the caller, or paths that are clearly owned by the provided
  phaseloop phase context.
- If ownership is unclear, fail without committing.
- If staged changes already exist, fail and leave them untouched.
- If the worktree was dirty before the phaseloop task started, do not commit
  those baseline-dirty paths unless the caller explicitly allows it. A
  phase-local commit may still commit phase-owned paths that were clean at task
  start.
- Push only when the caller explicitly requested push.

## Procedure

1. For a completed phaseloop task result, follow `phaseloop-result.md`.
2. For a phaseloop phase-local commit, inspect the phase file, task index, git
   status, and git diff. Stage only paths that clearly belong to that phase.
   If ownership is unclear, stop without committing.
3. If the caller provided explicit paths and a commit message, stage only those
   paths and commit with that message.
4. If neither path is deterministic, stop without committing and report why.
5. If push was explicitly requested, push after the commit succeeds.
