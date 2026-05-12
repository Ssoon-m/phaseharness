# Phaseharness Continuation

Continue the active phaseharness run from durable files only.

Run id: `{{RUN_ID}}`
Request: {{REQUEST}}
Current stage: `{{STAGE}}`
Required skill: `{{SKILL}}`
Run file: `{{RUN_PATH}}`
Required artifact: `{{ARTIFACT_PATH}}`
Loop: `{{LOOP_CURRENT}}` of `{{LOOP_COUNT}}`
Commit mode: `{{COMMIT_MODE}}`
Implementation phase: `{{IMPLEMENTATION_PHASE}}`
Implementation phase file: `{{IMPLEMENTATION_PHASE_PATH}}`
Reprompt of running stage: `{{REPROMPT}}`

## Controller Rules

- Use the required skill for this stage and perform only that stage.
- Rebuild context from `{{RUN_PATH}}`, artifacts, and phase files. Do not rely on conversation memory.
- Perform only the current stage in this turn. After updating state, stop normally so the Stop hook can request the next continuation prompt.
- Write or append the required artifact before marking work complete.
- Update state with `.phaseharness/bin/phaseharness-state.py` before ending. A completed stage must be recorded as `completed`; otherwise the Stop hook will re-enter the same stage.
- If the user explicitly asks to pause or stop the run, run `pause` and stop without advancing the stage.
- Only `clarify` may wait for missing user input with `wait-user`. If `clarify` requires a user decision, record the question in the artifact, run `wait-user --stage clarify`, and stop.
- For `context-gather`, `plan`, `generate`, and `evaluate`, do not pause for missing input; record assumptions, risks, or blockers in the artifact and continue the stage to completion or error.

## Stage Delegation

- `clarify`, `context-gather`, and `plan` are performed by the main session.
- `generate` and `evaluate` require one fresh subagent delegated by the main session. This continuation prompt authorizes that subagent call.
- The subagent must not call `.phaseharness/bin/phaseharness-state.py`.
- The subagent must not change run lifecycle state.
- The subagent must not commit.
- The subagent must return a final result and stop after its assigned work. It must not wait for follow-up work or start another stage.
- The main session remains the controller and records artifacts plus state after reviewing the subagent result.
- After receiving the subagent result, close, release, or terminate the subagent session if the provider supports it. If no explicit close action exists, send no further work to that subagent.

## Commit Handling

If this prompt is a commit prompt rather than a stage prompt, use the `commit` skill. The state runner and Stop hook never run `git commit`.
