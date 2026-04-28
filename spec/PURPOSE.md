# Purpose

This project defines and ships an installable agent harness standard that can run under both Claude Code and Codex.

The goal is not to generate a different automation system for every target repository. The goal is to provide:

- a canonical harness core
- installer documents that copy or merge that core into a target repository
- stable file contracts that survive runtime changes
- provider adapters for runtime-specific invocation details
- a five-phase artifact workflow for explicit work requests
- main-session clarify plus balanced headless session boundaries for analysis,
  build, and evaluate
- bridge sync hooks that keep generated Claude/Codex bridge files current
- an optional commit skill for completed workflow results
- explicit `none`, `final`, and `phase` commit modes, defaulting to `none`

## Target User Flow

1. A user opens an agent session inside a target repository.
2. The user gives the session `installer/install-harness.md`.
3. The agent installs this repository's canonical core into the target repository.
4. The target repository can then run the same harness lifecycle with Claude Code or Codex.

## Design Position

The harness treats files and git as the durable memory layer. It does not assume that a Claude or Codex conversation will keep enough context to continue safely.

The default runtime shape uses the interactive session for clarify, where user
questions and decisions belong. The harness then runs analysis, build, and
evaluate in fresh headless agent sessions, passing only durable artifacts
between those sessions.

The stable units are:

- state files in `tasks/`
- phase lifecycle rules
- phase artifacts for clarify, context gather, plan, generate, and evaluate
- session lifecycle rules for main-session clarify plus headless analysis,
  build, and evaluate
- provider-neutral prompt execution
- skill and role bridges generated from canonical sources
- hook adapters that call one shared bridge sync script
- commit boundaries that protect unrelated dirty worktree changes

## Non-goals

- Making `.claude/` or `.codex/` the standard source of truth
- Treating native subagent formats as portable
- Requiring identical prompt wording across Claude Code and Codex
- Retrying forever
- Continuing when required context is missing
- Depending on interactive approval prompts in headless mode

## Canonical Repository Shape

```text
<repo_root>/
  SPEC.md
  spec/
    PURPOSE.md
    CONTRACT.md
    PROVIDERS.md
    BRIDGES.md
  installer/
    install-harness.md
  core/
    .agent-harness/
      config.toml
      skills/
        phaseloop/
        commit/
      roles/
      prompts/
      providers/
    scripts/
      _utils.py
      gen-bridges.py
      gen-docs-diff.py
      install-hooks.py
      sync-bridges.py
      commit-result.py
      run-phases.py
      run-workflow.py
    templates/
      docs/
      tasks/
```

`core/` is the installable implementation. `installer/` explains how to install it. `spec/` documents the rules the implementation must preserve.
