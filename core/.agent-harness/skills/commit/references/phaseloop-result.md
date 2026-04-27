# Phaseloop Result Commits

Use this reference when committing a completed phaseloop task result or when
choosing a workflow commit mode.

## Completed Task Result

Prefer the deterministic task commit script:

```bash
python3 scripts/commit-result.py
```

To target a specific task:

```bash
python3 scripts/commit-result.py <task-dir>
```

For a custom message:

```bash
python3 scripts/commit-result.py <task-dir> --message "<type>: <summary>"
```

The script refuses automatic commits when:

- the task is not completed
- evaluation is not `pass` or `warn`
- `git HEAD` moved after the task started
- paths that were already dirty before phaseloop started are still dirty
- staged changes already exist

By default, `tasks/<task-dir>/artifacts/*` and other phaseloop task state are
excluded from product commits. Use `--include-harness-state` only when the user
explicitly wants phaseloop artifacts committed.

## Workflow Commit Modes

When starting a phaseloop workflow, do not auto-commit by default. Use
`--commit-mode none` unless the user chooses another mode.

Available modes:

- `none`: no automatic commit
- `final`: one commit after the whole workflow succeeds
- `phase`: one commit after each completed generate phase, using the commit
  skill with phase context; evaluation remains local task state and does not
  create an empty validation commit

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --max-attempts 2 --session-timeout-sec 600 --commit-mode none
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --max-attempts 2 --session-timeout-sec 600 --commit-mode final
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --max-attempts 2 --session-timeout-sec 600 --commit-mode phase
```

Use `--commit-message` only when the user gives a specific message or the
message can be inferred with high confidence from repository history. It is
valid only with `--commit-mode final`:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --max-attempts 2 --session-timeout-sec 600 --commit-mode final --commit-message "feat: add alarm settings"
```
