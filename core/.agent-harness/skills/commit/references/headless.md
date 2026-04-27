# Headless Commit Procedure

Use this reference when `AGENT_HEADLESS=1`.

Do not ask questions, wait for confirmation, or rely on interactive approval.
This procedure replaces the interactive flow.

## Rules

- Prefer no commit over a risky commit.
- Commit only paths selected by `scripts/commit-result.py` or paths explicitly
  listed by the caller.
- If ownership is unclear, fail without committing.
- If staged changes already exist, fail and leave them untouched.
- If the worktree was dirty before the phaseloop task started, fail unless the
  caller explicitly provided `--allow-baseline-dirty`.
- Push only when the caller explicitly requested push.

## Procedure

1. For a completed phaseloop task result, follow `phaseloop-result.md`.
2. If the caller provided explicit paths and a commit message, stage only those
   paths and commit with that message.
3. If neither path is deterministic, stop without committing and report why.
4. If push was explicitly requested, push after the commit succeeds.
