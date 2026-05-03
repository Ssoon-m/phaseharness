# Purpose

This repository defines and ships an installable `phaseharness` standard for
Claude Code and Codex.

The goal is to provide:

- one canonical target-directory root: `.phaseharness/`
- stable file state for five-phase repository work
- provider `SessionStart` bridge sync and `Stop` hook continuation
- explicit activation through the `phaseharness` skill
- explicit resume through the `phaseharness` skill after session interruption
- no loop activation for ordinary prompts
- Ralph-style build/evaluate loops driven by planned implementation phase files
- optional commit support for implementation phases or completed runs

## Target User Flow

1. A user opens Claude Code or Codex inside a target repository.
2. The user gives the session `installer/install-harness.md`.
3. The agent copies this repository's `core/.phaseharness/` into the target
   repository.
4. The installer adds provider `SessionStart`/`Stop` hook entries and skill bridges.
5. The user explicitly invokes the `phaseharness` skill for a concrete task.
6. The skill creates an active run file.
7. `SessionStart` hooks resync provider bridge files; `Stop` hooks continue
   the run through clarify, context gather, plan,
   implementation phase generation, and evaluate.
8. If evaluate fails and follow-up phase files exist within `loop_count`, the
   hook returns to generate for the next implementation phase queue.
9. If the conversation is interrupted, the user invokes the skill again to
   request resume; the hook binds the new session and continues from files.

## Canonical Repository Shape

```text
<repo_root>/
  SPEC.md
  spec/
  installer/
    install-harness.md
  core/
    .phaseharness/
      bin/
      hooks/
      skills/
      subagents/
      prompts/
      docs/
      state/
      runs/
```

`core/` is the installable implementation. `installer/` explains how to install
it. `spec/` documents the rules the implementation must preserve.
