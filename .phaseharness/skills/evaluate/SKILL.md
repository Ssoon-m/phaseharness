---
name: evaluate
description: Use when the user explicitly invokes evaluate, or when a phaseharness continuation asks for the evaluate stage. Delegates current diff verification to a fresh reviewer subagent and records pass, warn, or fail without product code edits.
---

# Evaluate

Evaluate verifies the current diff and records `pass`, `warn`, or `fail`. It does not modify product code.

## Run State

- If `evaluate` is run directly without a run id, create a manual run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode manual --stage evaluate --request "<request>" --commit-mode none --json
```

- Manual runs stop after this stage. Do not call `next`.

## Delegation Rules

- Standalone `evaluate` and auto phaseharness runs both use one fresh reviewer subagent.
- A `phaseharness` continuation prompt counts as explicit authorization to use that subagent for this stage.
- The main session remains the controller.
- The reviewer subagent must not modify product code.
- The reviewer subagent must not call `.phaseharness/bin/phaseharness-state.py`.
- The reviewer subagent must not commit.
- The reviewer subagent must return its final review and stop after this evaluation. It must not wait for follow-up work or start another stage.
- The main session reviews the reviewer result, writes the artifact, updates state, and closes or releases the subagent session if the provider supports it.
- If the provider has no explicit close or release action, the main session must treat the reviewer subagent's final response as terminal and send no further work to it.

## Inputs

Before creating the reviewer request, run:

```bash
python3 .phaseharness/skills/evaluate/scripts/render-evaluation-config.py --run-id <run-id>
```

If no run id is available, omit `--run-id`. Use the rendered output as the rendered evaluation config.

Document lines use `source` `(kind, priority, status)`: description. Status describes path/glob availability, not whether the guidance applies to the current diff.

For a phaseharness run, pass the reviewer relevant excerpts from `clarify.md`, `context.md`, `plan.md`, and `phases/*.md`, plus completed phases, current diff, validation commands, and the rendered evaluation config.

For standalone evaluate, do not fail only because phaseharness planning artifacts are missing. Build the review from the user's request, current diff and changed files, relevant repository patterns, discoverable validation commands, and the rendered evaluation config. Record missing artifacts as a risk only when they prevent a confident verdict.

## Review Criteria

Check the diff against:

- `clarify.md` success criteria
- `context.md` referenced documents, constraints, risks, and validation commands
- `plan.md` validation strategy
- `phases/*.md` acceptance criteria, boundaries, and validation commands
- rendered evaluation config

For every document line in the rendered evaluation config, record exactly one outcome:

- If relevant to the diff, record the concrete criterion under `Evaluation Checks`.
- If not relevant, record it under `Evaluation Checks` with `result: skipped`.
- If unavailable (`missing`, `no_matches`, `not_a_file`, `unreadable`, or `invalid`), record it under `Risks`.

Apply rule lines from the rendered evaluation config only when relevant or unconditional, and record outcomes under `Evaluation Checks`. The rendered evaluation config supplements run artifacts; it does not replace them and must not cause product code edits.

Priority semantics:

- A violated `required` evaluation criterion should usually be `fail`.
- A missing or partially satisfied `recommended` evaluation criterion should usually be `warn`.
- `optional` evaluation criteria should not affect the verdict unless they expose a concrete risk.

If the plan or phase files define validation commands, use those as the source of truth. Do not require extra commands from config.

## Verdicts

- `fail`: core requirement missing, runtime/type error, repository boundary violation, major UX breakage, or fatal validation risk.
- `warn`: usable but has test gaps, minor UX/convention drift, or follow-up risk.
- `pass`: no major issue against requirements and required validation passed.

## Follow-Up Phases

If verdict is `fail` and the issue is fixable, create new `.phaseharness/runs/<run-id>/phases/phase-NNN.md` files. Do not edit product code.

## Artifact

Write `.phaseharness/runs/<run-id>/artifacts/evaluate.md`:

```markdown
# Evaluate

## Verdict

## Findings

## Evaluation Checks

- source:
- requirement:
- result: pass | warn | fail | skipped
- evidence:

## Validation

## Risks

## Follow-Up Phases
```

Then record the result:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage evaluate completed --run-id <run-id> --evaluation-status pass
python3 .phaseharness/bin/phaseharness-state.py set-stage evaluate completed --run-id <run-id> --evaluation-status warn
python3 .phaseharness/bin/phaseharness-state.py set-stage evaluate completed --run-id <run-id> --evaluation-status fail
```
