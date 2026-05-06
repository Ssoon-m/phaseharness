# Phaseharness Continuation

Continue the active phaseharness run from durable files only.

Run id: `{{RUN_ID}}`
Current phase: `{{PHASE}}`
State file: `{{STATE_PATH}}`
Required artifact: `{{ARTIFACT_PATH}}`
Loop: `{{LOOP_CURRENT}}` of `{{LOOP_COUNT}}`
Attempt: `{{ATTEMPT}}` of `{{MAX_ATTEMPTS_PER_PHASE}}`
Commit mode: `{{COMMIT_MODE}}`
Claude subagent: `{{CLAUDE_SUBAGENT}}`
Codex subagent: `{{CODEX_SUBAGENT}}`
Implementation phase: `{{IMPLEMENTATION_PHASE}}`
Implementation phase file: `{{IMPLEMENTATION_PHASE_PATH}}`
Resume summary: {{RESUME_SUMMARY}}

## Mandatory Subagent Call

- Do not execute this phase in the parent conversation.
- Your first action must be to invoke exactly one provider-native phaseharness subagent for this phase.
- Codex: directly spawn exactly one custom agent named `{{CODEX_SUBAGENT}}`, wait for it to finish, then report its result. Do not spawn multiple agents for the same phase.
- Claude Code: directly invoke the `{{CLAUDE_SUBAGENT}}` subagent, wait for it to finish, then report its result.
- Pass the run id, current phase, state file, required artifact, loop values, commit mode, implementation phase, and implementation phase file to the subagent.
- When the provider-native subagent returns with completed or error state, immediately perform any provider-supported close/release action for that subagent thread. Codex must call `close_agent` when the spawned agent id is available. Claude Code treats a returned subagent invocation as closed, but if the environment exposes an explicit close/release action, call it.
- Close/release failures are not phase failures. Record them only in the parent summary, then continue with artifact/state inspection.
- After the subagent returns, the parent conversation may only inspect the required artifact and state file, summarize the subagent result, and stop. Do not complete phase work in the parent conversation.
- If the provider cannot invoke the subagent, create or append the required artifact with an `## Executor` section, set this phase to `waiting_user` with an error message that starts with `subagent_unavailable`, and stop.
- The required artifact must include an `## Executor` section with `requested_subagent`, `execution_mode`, and `delegation_error`.

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
- Commit mode is already stored in state. `none` does not commit. `phase` and `final` commit points are handled by a separate Stop-hook continuation that requires the installed `commit` skill.

## Subagent Instructions

{{SUBAGENT_INSTRUCTIONS}}
