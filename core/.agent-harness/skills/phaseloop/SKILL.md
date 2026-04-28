---
name: phaseloop
description: Run a staged workflow that clarifies, contextualizes, plans, implements, and evaluates a concrete repository task.
---

# Phaseloop

Use this skill when the user asks to clarify, scope, plan, implement, or
evaluate a concrete repository task through a staged workflow. The user does
not need to mention phaseloop by name.

Common triggers:

- Clarify an ambiguous implementation request before coding.
- Turn a request into scope, assumptions, non-goals, and done conditions.
- Gather repository context before planning or implementation.
- Plan and implement a concrete repository change in phases.
- Independently evaluate completed work against acceptance criteria.

Do not use this skill for a short answer, pure explanation, code review, or
one-off terminal command unless the user asks for a staged workflow.

## Default Behavior

Clarify in the current conversation, then run the headless workflow runner for
the remaining phases. Do not delegate clarify to a headless session.

The default session strategy is balanced:

1. `clarify` main session: asks the user material questions, captures decisions,
   and writes the clarify artifact.
2. `analysis` headless session: writes context, plan, and phase files from the
   clarify artifact.
3. `build` headless sessions: execute planned implementation phases.
4. `evaluate` headless session: verifies the result independently.

This keeps user-facing ambiguity in the main session while avoiding a new agent
session for every later logical phase.

## Start Rules

1. Identify the concrete request.
2. Run main-session clarify before starting the headless runner.
   - Use the `phase-clarify` role as the artifact contract.
   - Ask concise grouped questions when answers would materially change
     implementation.
   - Prefer three to seven questions across these categories: feasibility and
     constraints, UX and workflow, data and state, scope and phasing,
     dependencies and integrations, validation.
   - If the request is already clear enough, ask no questions and record that no
     user question was required.
   - After the user answers, write the clarify artifact to a local temporary
     markdown file, for example `tasks/.phaseloop-clarify.md`; create the
     parent directory if needed.
3. Determine `--max-attempts` before starting the headless runner.
   - If the user already specified it, use that value.
   - If not, ask once: `How many attempts should each phase get? Default is 2.`
   - Do not start the workflow until the user chooses a number or explicitly accepts the default.
4. Determine `--commit-mode` before starting.
   - If the user already specified `none`, `final`, or `phase`, use that value.
   - If not, ask once: `Commit mode for this phaseloop task? none, final, or phase. Default is none.`
   - `none`: do not commit automatically.
   - `final`: create one commit after the whole workflow succeeds.
   - `phase`: create commits after completed generate phases.
   - If the user does not choose and accepts the default, use `none`.
5. Use `--session-timeout-sec 600` unless the user or repository context suggests a different value.
6. Run:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --clarify-file <clarify-file> --max-attempts <attempts> --session-timeout-sec 600 --commit-mode <mode>
```

Provider-specific examples:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --clarify-file tasks/.phaseloop-clarify.md --provider codex --max-attempts 2 --session-timeout-sec 600 --commit-mode none
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --clarify-file tasks/.phaseloop-clarify.md --provider claude --max-attempts 2 --session-timeout-sec 600 --commit-mode final
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --clarify-file tasks/.phaseloop-clarify.md --provider codex --max-attempts 2 --session-timeout-sec 600 --commit-mode phase
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
started dirty; unrelated staged changes still fail closed. If a phase has no
product changes to commit, phaseloop treats the commit step as successful and
does not create an empty commit.

Commit message rules:

- Describe the work itself.
- Do not mention phase numbers.
- Do not mention `tasks/`, artifacts, or phaseloop internal paths.
- Do not list changed files.
- Prefer the repository's recent commit style; otherwise use `<type>: <summary>`.

## Workflow

Logical phases:

1. `clarify`: convert the request into an execution contract: scope, user
   decisions, assumptions, non-goals, and done conditions.
2. `context gather`: collect only the repository facts needed to act on that
   contract: relevant files, patterns, constraints, risks, and validation
   commands.
3. `plan`: turn the contract and context into ordered implementation phases
   with concrete acceptance criteria.
4. `generate`: execute the planned phases, validate when possible, and record
   results without reopening clarification or planning.
5. `evaluate`: independently check the completed work against done conditions
   and acceptance criteria, then report pass, warn, or fail.

Provider session boundaries:

- `clarify`: runs in the current conversation and produces the first artifact.
- `analysis`: runs `context gather` and `plan` together.
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
- Do ask clarification questions in the main session before the headless runner
  when answers would materially affect implementation.
- In an interactive agent session, require a user-selected `--max-attempts`
  value or explicit acceptance of the default before running.
- In an interactive agent session, require a user-selected `--commit-mode`
  value or explicit acceptance of default `none` before running.
- Use the current conversation to clarify, start the runner, monitor output, and
  report the resulting artifacts.
- If the request is too broad, clarify should choose or ask for the smallest
  useful increment and record deferred scope.
- Respect `--max-attempts`; do not retry forever.
- Do not push.
- Default to `--commit-mode none`.
