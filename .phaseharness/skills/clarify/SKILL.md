---
name: clarify
description: Use when the user explicitly invokes clarify, or when a phaseharness continuation asks for the clarify stage. Turns a request into executable requirements, success criteria, scope, non-goals, decisions, assumptions, and open questions without implementation.
---

# Clarify

Clarify converts the user request into an executable contract. It does not implement, plan phases, or deeply inspect the repository.

## Run State

- If a phaseharness continuation supplied a run id, use that run.
- If the user invoked `clarify` directly without a run id, create a manual run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode manual --stage clarify --request "<request>" --commit-mode none --json
```

- Manual runs perform only this stage. Do not call `next`.
- Auto runs are continued only by the Stop hook through `next --require-auto --reprompt-running --require-session-binding --json`.

## Rules

- Do not modify product code.
- Do not perform deep repository investigation.
- Do not ask questions for facts that can be discovered from repository files.
- Ask only user decisions that would change implementation, scope, risk, or acceptance criteria.
- If user input is required, write the question into the artifact and run:

```bash
python3 .phaseharness/bin/phaseharness-state.py wait-user --stage clarify --run-id <run-id> --message "<question>"
```

## Artifact

Write `.phaseharness/runs/<run-id>/artifacts/clarify.md`:

```markdown
# Clarify

## Request

## Goal

## Success Criteria

## Scope

## Non-Goals

## User Decisions

## Assumptions

## Open Questions

## Recommended Next Step
```

When the artifact is complete:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage clarify completed --run-id <run-id>
```
