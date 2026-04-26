# Rollback Prompt

You are rolling back a failed build step.

The orchestrator provides:

- iteration id
- pre-build commit SHA
- check report path

Rules:

- Do not ask the user questions when `AGENT_HEADLESS=1`.
- Do not push.
- Verify the target commit exists.
- Run `git reset --hard <pre-build-sha>`.
- Verify `git rev-parse HEAD` matches the target SHA.
- Create an empty marker commit only if the orchestrator requested one.
- If rollback is blocked, record `runtime_error` or `sandbox_blocked` in the rollback output.
