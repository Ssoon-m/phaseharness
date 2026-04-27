# Interactive Commit Procedure

Use this reference when `AGENT_HEADLESS` is not `1`.

## Procedure

1. Inspect repository state:

```bash
git status --short
git diff --stat
git log --oneline -15
git branch --show-current
```

2. Classify changed files:

- `IN`: changed for the current request
- `UNKNOWN`: unclear ownership
- `OUT`: unrelated local changes

3. Ask the user before committing `UNKNOWN` files. Exclude `OUT` files.

4. Stage only `IN` files by explicit path:

```bash
git add path/to/file path/to/other-file
git diff --cached --stat
```

5. Choose the commit message using `message-guidance.md`.

6. Commit:

```bash
git commit -m "<type>: <summary>"
```

7. Report the created commit hash and any files intentionally left unstaged.

8. If push was requested:

```bash
git push
```

If upstream is missing:

```bash
git push -u origin <branch>
```
