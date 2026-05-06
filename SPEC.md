# SPEC

## 1. Purpose

phaseharness ships an installable `phaseharness` workflow for Claude Code and
Codex.

The target repository receives one canonical harness directory:

```text
.phaseharness/
```

The workflow is explicit and file based. Conversation memory is not the
contract; phase state and artifacts are.

## 2. Activation

The installed `SessionStart` hooks are allowed to resync provider bridge files
from `.phaseharness/`. They must not create, resume, or advance runs.

The installed `Stop` hooks are always allowed to run, but the loop is disabled
by default.

The hook may continue work only when:

- `.phaseharness/state/active.json` exists
- `status` is `active`
- `activation_source` is `phaseharness_skill`
- `active_run` points to a run under `.phaseharness/runs/`

Only the `phaseharness` skill may create or activate a run. Normal questions,
short explanations, reviews, and one-off commands must not start the loop.

Before a new run starts, the skill must determine `loop_count`,
`max_attempts_per_phase`, and `commit_mode`. If the user omitted any value, the
skill asks once and waits for a chosen value or explicit default acceptance.
`loop_count` is the maximum number of `generate -> evaluate` cycles.
`max_attempts_per_phase` is the retry budget for each planned implementation
phase and executable phase prompt.

If a later provider session needs to continue an interrupted run, the user must
explicitly invoke the `phaseharness` skill again. The skill records a resume
request in the run state; the next `Stop` hook then binds the new provider
session and continues from files.

## 3. Workflow

The workflow order is fixed:

```text
clarify -> context gather -> plan -> generate -> evaluate
```

Phase artifacts:

- `.phaseharness/runs/<run-id>/artifacts/01-clarify.md`
- `.phaseharness/runs/<run-id>/artifacts/02-context.md`
- `.phaseharness/runs/<run-id>/artifacts/03-plan.md`
- `.phaseharness/runs/<run-id>/artifacts/04-generate.md`
- `.phaseharness/runs/<run-id>/artifacts/05-evaluate.md`

Run state:

- `.phaseharness/state/active.json`
- `.phaseharness/state/index.json`
- `.phaseharness/runs/<run-id>/state.json`
- `.phaseharness/runs/<run-id>/phases/phase-NNN.md`
- `.phaseharness/runs/<run-id>/outputs/stop-<turn>.json`
- session metadata inside `.phaseharness/runs/<run-id>/state.json`

## 4. Repository Layout

Source repository:

```text
<repo_root>/
  SPEC.md
  spec/
  installer/
    install-harness.md
  core/
    .phaseharness/
      config.toml
      .gitignore
      bin/
      hooks/
      skills/
      subagents/
      prompts/
      state/
      runs/
```

Target repository after install:

```text
<target_repo>/
  .phaseharness/
    config.toml
    .gitignore
    bin/
      phaseharness-hook.py
      phaseharness-sync-bridges.py
      phaseharness-state.py
      commit-result.py
    hooks/
      claude-session-start.sh
      claude-stop.sh
      codex-session-start.sh
      codex-stop.sh
    skills/
      phaseharness/
        SKILL.md
      commit/
        SKILL.md
    subagents/
    prompts/
    state/
    runs/

  .claude/settings.json
  .claude/skills/phaseharness -> ../../.phaseharness/skills/phaseharness
  .claude/skills/commit -> ../../.phaseharness/skills/commit
  .claude/agents/phaseharness-*.md
  .agents/skills/phaseharness -> ../../.phaseharness/skills/phaseharness
  .agents/skills/commit -> ../../.phaseharness/skills/commit
  .codex/config.toml
  .codex/hooks.json
  .codex/agents/phaseharness-*.toml
```

The provider files outside `.phaseharness/` are bridge/config requirements only.
They are not canonical harness source.

## 5. Hook Contract

Claude Code and Codex both use a `SessionStart` hook to resync provider bridge
files and a `Stop` hook to decide whether the agent should continue.

The SessionStart hook:

- reads `.phaseharness/config.toml`, `.phaseharness/subagents/`, and the
  canonical skill
- regenerates provider hook, skill, and subagent bridge files silently
- does not create or continue workflow runs

The Stop hook:

- reads stdin JSON from the provider
- finds `.phaseharness/`
- no-ops unless the activation gate is satisfied
- locks `.phaseharness/state/hook.lock`
- reads active run state
- advances only one phase at a time
- returns `{"decision":"block","reason":"<continuation prompt>"}` to continue
- no-ops when the run is completed, errored, or waiting for user input
- no-ops when a different provider session appears without an explicit resume
  request
- consumes `max_attempts_per_phase` when an implementation phase or executable
  phase prompt is still running or needs retry
- consumes `loop_count` when `evaluate` fails and queues follow-up
  implementation phases
- applies `commit_mode` by prompting the parent agent to use the installed
  `commit` skill after each implementation phase (`phase`) or after pass/warn
  `evaluate` (`final`)

Codex no-op output is JSON. Claude no-op output is empty stdout.

## 6. Guardrails

- Activation is explicit through the `phaseharness` skill.
- Provider hooks only continue active runs recorded in `.phaseharness/state/`.
- Retry and loop budgets are finite.
- Runs stop while user input is required.

## 7. Verification

Required local checks:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/.phaseharness/bin/*.py tests/smoke_install.py
```
