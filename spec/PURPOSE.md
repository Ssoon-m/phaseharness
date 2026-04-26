# Purpose

This project defines and ships an installable agent harness standard that can run under both Claude Code and Codex.

The goal is not to generate a different automation system for every target repository. The goal is to provide:

- a canonical harness core
- installer documents that copy or merge that core into a target repository
- stable file contracts that survive runtime changes
- provider adapters for runtime-specific invocation details
- a five-phase artifact workflow for explicit work requests

## Target User Flow

1. A user opens an agent session inside a target repository.
2. The user gives the session `installer/install-harness.md`.
3. The agent installs this repository's canonical core into the target repository.
4. The target repository can then run the same harness lifecycle with Claude Code or Codex.

## Design Position

The harness treats files and git as the durable memory layer. It does not assume that a Claude or Codex conversation will keep enough context to continue safely.

The stable units are:

- state files in `tasks/`
- phase lifecycle rules
- phase artifacts for clarify, context gather, plan, generate, and evaluate
- provider-neutral prompt execution
- skill and role bridges generated from canonical sources

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
      roles/
      prompts/
      providers/
    scripts/
      _utils.py
      gen-bridges.py
      gen-docs-diff.py
      run-phases.py
      run-workflow.py
    templates/
      docs/
```

`core/` is the installable implementation. `installer/` explains how to install it. `spec/` documents the rules the implementation must preserve.
