# Phaseharness Continuation

Continue the active phaseharness run from durable files only.

Run id: `{{RUN_ID}}`
Current phase: `{{PHASE}}`
State file: `{{STATE_PATH}}`
Required artifact: `{{ARTIFACT_PATH}}`
Loop: `{{LOOP_CURRENT}}` of `{{LOOP_COUNT}}`
Attempt: `{{ATTEMPT}}` of `{{MAX_ATTEMPTS_PER_PHASE}}`
Commit mode: `{{COMMIT_MODE}}`
Implementation phase: `{{IMPLEMENTATION_PHASE}}`
Implementation phase file: `{{IMPLEMENTATION_PHASE_PATH}}`
Resume summary: {{RESUME_SUMMARY}}

## Rules

- Read the state file and all earlier artifacts before acting.
- If this is a resumed session, reconstruct context from `.phaseharness/runs/<run-id>/state.json`, previous artifacts, and the resume summary. Do not rely on prior conversation memory.
- Work only on the current phase.
- Do not ask the user questions unless the state is explicitly `waiting_user`.
- If user input is required, set run status to `waiting_user`, set `needs_user` to `true`, record the question in the current artifact, and stop.
- Before ending the turn, update the current phase status in `state.json`.
- When the phase is complete, write the required artifact and set that phase to `completed`.
- During `generate`, work only on the listed implementation phase file. Mark that implementation phase completed or error in `state.json`; do not mark top-level `generate` completed yourself.
- During `evaluate`, `fail` should add one or more follow-up `phases/phase-NNN.md` files when the issue is fixable within the remaining loop budget.
- On failure, set the phase to `error` and include a clear `error_message`.
- Do not start another phase yourself. The Stop hook advances phases from file state.
- Commit mode is already stored in state. `none` does not commit, `phase` commits product changes after each implementation phase, and `final` commits product changes after a pass/warn `evaluate`.

## Subagent Instructions

{{SUBAGENT_INSTRUCTIONS}}
