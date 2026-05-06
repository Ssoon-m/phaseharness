---
name: commit
description: Safely create git commits and optionally push them. Use when the user asks to commit current work, commit selected changes, create logical commits, or commit and push.
---

# Commit

Use this workflow when the user asks to commit work.

## Rules

- Commit only changes related to the current task or files explicitly named by the user.
- Exclude unrelated changes, secrets, local config, logs, generated artifacts, dependency folders, and large binaries unless explicitly requested.
- Ask before staging ambiguous files or committing directly on `main` or `master`.
- Split unrelated logical changes into separate commits.
- Never use `git add .`, `git add -A`, or `--no-verify`.
- Push only when explicitly requested.

## Workflow

Inspect:

```bash
git status --short
git diff --stat
git log --oneline -15
git branch --show-current
```

Stage explicit paths or hunks:

```bash
git add <path1> <path2>
git add -p <path>
git diff --cached --stat
```

Commit using the repository's existing message style:

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <summary>

<body only when useful>
EOF
)"
```

Verify:

```bash
git log --oneline -<N>
git status
```

Push only if requested:

```bash
git push
git push -u origin <current-branch>
```

Report commits created, push status, excluded files, and any remaining changes.

## Phaseharness Commit Mode

When a phaseharness Stop hook asks you to use this skill, run the exact
`.phaseharness/bin/commit-result.py` helper command from the continuation
prompt. That helper applies the phaseharness commit guardrails, excludes
runtime state and provider bridge files, creates the product commit, and records
the result in `.phaseharness/runs/<run-id>/state.json`.

Do not push. After the helper succeeds or fails, stop so the next Stop hook can
continue from file state.
