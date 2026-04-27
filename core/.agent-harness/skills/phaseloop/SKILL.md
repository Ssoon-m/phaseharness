---
name: phaseloop
description: Run an explicit work request through the phaseloop artifact workflow.
---

# Phaseloop

Use this skill when the user asks to implement a concrete request through the
phaseloop harness.

## Default Behavior

Run the headless workflow runner. Do not manually perform the workflow in the
current conversation unless the user explicitly asks for manual debugging.

The default session strategy is balanced:

1. `analysis` headless session: writes clarify, context, plan, and phase files.
2. `build` headless sessions: execute planned implementation phases.
3. `evaluate` headless session: verifies the result independently.

This keeps the current conversation as a thin orchestrator while avoiding a new
agent session for every small logical phase.

## Start Rules

1. Identify the concrete request.
2. Determine `--max-attempts` before starting.
   - If the user already specified it, use that value.
   - If not, ask once: `How many attempts should each phase get? Default is 2.`
   - Do not start the workflow until the user chooses a number or explicitly accepts the default.
3. Determine `--commit-mode` before starting.
   - If the user already specified `none`, `final`, or `phase`, use that value.
   - If not, ask once: `Commit mode for this phaseloop task? none, final, or phase. Default is none.`
   - `none`: do not commit automatically.
   - `final`: create one commit after the whole workflow succeeds.
   - `phase`: create commits after completed generate phases.
   - If the user does not choose and accepts the default, use `none`.
4. Use `--session-timeout-sec 600` unless the user or repository context suggests a different value.
5. Run:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --max-attempts <attempts> --session-timeout-sec 600 --commit-mode <mode>
```

Provider-specific examples:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --provider codex --max-attempts 2 --session-timeout-sec 600 --commit-mode none
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --provider claude --max-attempts 2 --session-timeout-sec 600 --commit-mode final
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --provider codex --max-attempts 2 --session-timeout-sec 600 --commit-mode phase
```

`--max-attempts` is the retry budget for each workflow session and implementation
phase. It is not an infinite loop count.

`--commit-mode` defaults to `none`. `final` runs `scripts/commit-result.py`
only after evaluation passes or warns. `phase` asks the commit skill to commit
after each completed generate phase using the phase file and task index as
context. Evaluation remains local task state and does not create an empty
validation commit. Product commits exclude phaseloop artifacts by default;
commit subjects come from the work request or phase metadata. Phase commits
should include only paths clearly owned by that phase, even if the repository
started dirty; unrelated staged changes still fail closed.

Commit message rules:

- Describe the work itself.
- Do not mention phase numbers.
- Do not mention `tasks/`, artifacts, or phaseloop internal paths.
- Do not list changed files.
- Prefer the repository's recent commit style; otherwise use `<type>: <summary>`.

## Workflow

Logical phases:

1. `clarify`: understand the request, done conditions, assumptions, and non-goals.
2. `context gather`: find relevant docs, code, patterns, and constraints.
3. `plan`: create task state and implementation phase files.
4. `generate`: execute the planned phases.
5. `evaluate`: verify the result against done conditions and acceptance criteria.

Provider session boundaries:

- `analysis`: runs `clarify`, `context gather`, and `plan` together.
- `build`: runs planned implementation phases from `phase<N>.md`.
- `evaluate`: runs final verification separately from build.

Artifacts:

- `tasks/<task-dir>/artifacts/01-clarify.md`
- `tasks/<task-dir>/artifacts/02-context.md`
- `tasks/<task-dir>/artifacts/03-plan.md`
- `tasks/<task-dir>/artifacts/04-generate.md`
- `tasks/<task-dir>/artifacts/05-evaluate.md`

Rules:

- Do not ask questions when `AGENT_HEADLESS=1`.
- In an interactive agent session, require a user-selected `--max-attempts`
  value or explicit acceptance of the default before running.
- In an interactive agent session, require a user-selected `--commit-mode`
  value or explicit acceptance of default `none` before running.
- Use the current conversation only to start the runner, monitor output, and
  report the resulting artifacts.
- If the request is too broad, the analysis session should choose the smallest
  useful increment and record deferred scope.
- Respect `--max-attempts`; do not retry forever.
- Do not push.
- Default to `--commit-mode none`.
