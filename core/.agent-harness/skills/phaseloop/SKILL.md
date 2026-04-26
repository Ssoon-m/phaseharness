---
name: phaseloop
description: Run an explicit work request through the five-phase phaseloop artifact workflow.
---

# Phaseloop

Use this skill when the user asks to implement a concrete request through the
phaseloop harness.

Primary command:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --max-attempts 2
```

Provider-specific examples:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --provider codex --max-attempts 2
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "<request>" --provider claude --max-attempts 2
```

Workflow:

1. Clarify the request into goal, done conditions, assumptions, and non-goals.
2. Gather relevant repository context.
3. Plan task state and implementation phases.
4. Generate the implementation by running phase files.
5. Evaluate the result against done conditions and acceptance criteria.

Artifacts:

- `tasks/<task-dir>/artifacts/01-clarify.md`
- `tasks/<task-dir>/artifacts/02-context.md`
- `tasks/<task-dir>/artifacts/03-plan.md`
- `tasks/<task-dir>/artifacts/04-generate.md`
- `tasks/<task-dir>/artifacts/05-evaluate.md`

Rules:

- Prefer `scripts/run-workflow.py` over manually orchestrating phases.
- Do not ask questions when `AGENT_HEADLESS=1`.
- If the request is too broad, clarify the smallest useful increment and record
  the deferred scope.
- Respect `--max-attempts`; do not retry forever.
- Do not push.
