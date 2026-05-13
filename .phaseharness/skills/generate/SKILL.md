---
name: generate
description: Use when the user explicitly invokes generate for an existing phase file, or when a phaseharness continuation asks for the generate stage. Implements exactly one planned phase and is not a general implementation request handler.
---

# Generate

Generate implements exactly one planned phase file. It is not used for ordinary direct implementation requests.

## Preconditions

- A run id must exist.
- A phase file such as `.phaseharness/runs/<run-id>/phases/phase-001.md` must exist.
- If no plan or phase file exists, do not implement. Explain the missing prerequisite.

## Controller Rules

- In an auto phaseharness run, the main session is the controller and must delegate implementation to one fresh implementer subagent.
- A `phaseharness` continuation prompt counts as explicit authorization to use that subagent for this stage.
- The subagent implements one phase only.
- The subagent must not call `.phaseharness/bin/phaseharness-state.py`.
- The subagent must not commit.
- The subagent must return its final result and stop after the assigned phase. It must not wait for follow-up work or start another phase.
- The main session reviews the subagent result, appends `artifacts/generate.md`, updates state, and closes or releases the subagent session if the provider supports it.
- If the provider has no explicit close or release action, the main session must treat the subagent's final response as terminal and send no further work to it.

## Implementer Context Pack

Pass the subagent:

- `run_id`
- `phase_id`
- full phase file
- necessary excerpts from `clarify.md`, `context.md`, and `plan.md`
- target files
- allowed changes
- forbidden changes
- validation commands
- expected output: changed files, validations run, remaining risks, artifact summary, then stop

## Implementation Rules

- Follow the phase file's `Target Files`, `Allowed Changes`, and `Forbidden Changes`.
- Do not modify product files outside phase scope.
- Do not start another phase.
- Do not change run lifecycle state from the subagent.
- If auto `commit_mode` is `phase` or `final`, wait for the state runner commit prompt. Do not commit here.

## Verification Boundary

- Do not call, simulate, or perform the `evaluate` stage from `generate`.
- Run only minimal phase-scoped checks needed to avoid handing off obviously broken work.
- Prefer fast checks tied directly to changed files or explicitly required by the phase.
- Do not run broad repository-wide review or exhaustive validation unless the phase file explicitly requires it for generation.
- Record any skipped expensive validation commands in the artifact for `evaluate` to consider.

## Artifact

Append to `.phaseharness/runs/<run-id>/artifacts/generate.md`:

```markdown
## <phase-id>

### Summary

### Changed Files

### Validation

### Risks
```

On success:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-generate-phase <phase-id> completed --run-id <run-id>
```

On failure:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-generate-phase <phase-id> error --run-id <run-id> --message "<failure summary>"
```
