# Build Prompt

You are running the build step for one harness iteration.

Inputs are provided by the orchestrator, including the iteration id and requirement file path.

Required flow:

1. Read the requirement file.
2. Read `docs/mission.md`, `docs/spec.md`, `docs/testing.md`, and `docs/user-intervention.md` when present.
3. Inspect the repository enough to produce a grounded plan.
4. If a `tech-critic-lead` role is available, use the provider role contract to review the plan before implementation.
5. Create task and phase files using `.agent-harness/prompts/task-create.md`.
6. Run `python3 scripts/run-phases.py <task-dir>`.
7. Stop if any phase records `error`.

Headless rules:

- Do not ask the user questions when `AGENT_HEADLESS=1`.
- If required context is missing, record `context_insufficient` in the relevant state file and stop.
- Do not rely on runtime-specific subagent auto-routing.
- Do not push.
