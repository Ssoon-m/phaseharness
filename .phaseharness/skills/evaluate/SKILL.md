---
name: evaluate
description: Use when the user explicitly invokes evaluate, or when a phaseharness continuation asks for the evaluate stage. Delegates current diff verification to a fresh reviewer subagent and records pass, warn, or fail without product code edits.
---

# Evaluate

Evaluate verifies the current diff against the run contract. By default, it does not modify product code.

## Controller Rules

- If `evaluate` is run directly without a run id, create a manual run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode manual --stage evaluate --request "<request>" --commit-mode none --json
```

- Manual runs stop after this stage. Do not call `next`.
- Standalone `evaluate` and auto phaseharness runs both use one fresh reviewer subagent.
- A `phaseharness` continuation prompt counts as explicit authorization to use that subagent for this stage.
- The main session remains the controller.
- The reviewer subagent must not modify product code.
- The reviewer subagent must not call `.phaseharness/bin/phaseharness-state.py`.
- The reviewer subagent must not commit.
- The reviewer subagent must return its final review and stop after this evaluation. It must not wait for follow-up work or start another stage.
- The main session reviews the reviewer result, writes the artifact, updates state, and closes or releases the subagent session if the provider supports it.
- If the provider has no explicit close or release action, the main session must treat the reviewer subagent's final response as terminal and send no further work to it.

## Reviewer Context Pack

Pass the reviewer:

- `run_id`
- `clarify.md` excerpts: `Request`, `Goal`, `Success Criteria`, `User Decisions`
- `context.md` excerpts: `Referenced Documents`, `Constraints`, `Risks`, `Validation Commands`
- `plan.md` and `phases/*.md` excerpts: `Target Files`, `Acceptance Criteria`, `Validation Commands`
- completed phase list
- current diff summary or necessary diff text
- validation commands to run
- expected output: `pass | warn | fail`, findings, evidence, follow-up phase suggestions, then stop

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

## Evidence

## Validation

## Follow-Up Phases
```

Then record the result:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage evaluate completed --run-id <run-id> --evaluation-status pass
python3 .phaseharness/bin/phaseharness-state.py set-stage evaluate completed --run-id <run-id> --evaluation-status warn
python3 .phaseharness/bin/phaseharness-state.py set-stage evaluate completed --run-id <run-id> --evaluation-status fail
```
