---
name: commit
description: Use when the user explicitly asks to commit, or when a phaseharness commit prompt asks for a meaningful manual commit for commit_mode phase or final.
---

# Commit

Commit is the only path that creates git commits for phaseharness commit prompts. The state runner and Stop hook never commit.

## General Rules

- Inspect before staging:

```bash
git status --short
git diff --stat
git diff -- <eligible-path>
```

- Stage only files related to the requested commit.
- Never use `git add .`, `git add -A`, or `--no-verify`.
- Do not include unrelated user changes.
- Do not include skipped baseline paths.
- Do not include runtime state or provider bridge files from the commit prompt.
- For ordinary user-requested commits, stop and ask if staged changes already exist or scope is ambiguous.
- For phaseharness commit prompts, do not ask or pause the workflow when commit scope is unsafe or ambiguous; record `skipped` and continue.
- Do not push unless the user explicitly asked.

## Phaseharness Commit Prompts

When the prompt includes `Run id`, `Commit key`, `Commit mode`, `Eligible Paths`, and `Skipped Baseline Paths`:

1. Inspect `git status` and diffs for eligible paths only.
2. If there are meaningful eligible changes, stage those paths or hunks and commit with a meaningful message.
3. If no eligible changes exist, record `no_changes`.
4. If committing would be unsafe or the scope is ambiguous, do not commit; record `skipped`.
5. If commit fails, record `failed`.

Message shape:

```text
<type>: <meaningful summary>

- <meaningful detail>
- <meaningful detail>
```

Do not use fixed messages like `chore: complete phase-001`.

After handling the prompt, run exactly one state command:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-commit <commit-key> committed --run-id <run-id>
python3 .phaseharness/bin/phaseharness-state.py set-commit <commit-key> no_changes --run-id <run-id> --message "no eligible changes to commit"
python3 .phaseharness/bin/phaseharness-state.py set-commit <commit-key> skipped --run-id <run-id> --message "<unsafe or ambiguous commit scope>"
python3 .phaseharness/bin/phaseharness-state.py set-commit <commit-key> failed --run-id <run-id> --message "<failure summary>"
```
