# Check Prompt

You are checking the result of one harness iteration.

Read:

- the current iteration requirement
- `tasks/index.json`
- the most recent task index
- each `phase<N>-output.json` for the task
- relevant docs and diffs

Write `iterations/<iter-id>/check-report.json` with valid JSON:

```json
{
  "iter_id": "<iter-id>",
  "status": "pass",
  "task": {
    "dir": "tasks/<task-dir>",
    "name": "<task-name>",
    "overall_status": "completed"
  },
  "phases": [],
  "issues": [],
  "conclusion": "",
  "carry_over": [],
  "progress": {
    "previous_iter_id": null,
    "signal": "no_prior_run",
    "summary": ""
  }
}
```

Status rules:

- `pass`: all phases completed and acceptance criteria evidence is credible.
- `warn`: all phases completed but there is residual risk or weak evidence.
- `fail`: a phase failed, task was not created, or implementation is clearly incomplete.

Do not ask the user questions in headless mode.
