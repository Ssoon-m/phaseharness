# Commit Message Guidance

Use the repository's recent commit style when it is clear. If there is no strong
local style, use a concise subject:

```text
<type>: <work summary>
```

Examples:

```text
feat: add alarm settings
fix: handle expired session refresh
docs: update deployment notes
test: cover alarm scheduling
chore: validate alarm settings
```

Rules:

- Describe the user-visible or maintenance work, not the phaseloop mechanics.
- Do not mention phase numbers.
- Do not mention `tasks/`, artifacts, or phaseloop internal paths.
- Do not list changed files in the message.
- Prefer no body. Add a body only when the repository style or the work itself
  clearly needs one.
- For `phase` commit mode, each planned phase should set a `commit_message` in
  `tasks/<task-dir>/index.json`; use that message as-is when it matches the
  actual phase change.
- Do not create empty validation commits in `phase` mode.
