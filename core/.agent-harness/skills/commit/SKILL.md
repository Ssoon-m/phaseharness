---
name: commit
description: Commit phaseloop or current-session changes safely, with optional push only when the user explicitly asks.
---

# Commit

Use this skill when the user asks to commit, git commit, commit and push, or
commit the result of a completed phaseloop task.

## Preflight

Before applying any other section, determine whether this session is headless:

```bash
echo "AGENT_HEADLESS=${AGENT_HEADLESS:-0}"
```

Then follow only the relevant procedure:

- If the output is `AGENT_HEADLESS=1`, read and follow
  `references/headless.md`.
- Otherwise, read and follow `references/interactive.md`.

Load these references only when needed:

- `references/phaseloop-result.md` for completed phaseloop task results or
  workflow commit modes.
- `references/message-guidance.md` when choosing or reviewing a commit message.

## Always

- Commit only changes that belong to the current request.
- Do not run `git add .` or `git add -A` at repository root.
- Push only when the user explicitly asks for push.
- Do not use `--no-verify`.
- Do not commit secrets, local env files, logs, build output, dependency
  directories, or unrelated local changes.
