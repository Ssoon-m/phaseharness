# phaseloop

Installable `phaseharness` workflow for Claude Code and Codex.

This repository ships a canonical harness that is copied into a target
repository under `.phaseharness/`. The installed harness uses provider `Stop`
hooks and durable files to continue a task through:

```text
clarify -> context gather -> plan -> generate -> evaluate
```

The hook is installed at the provider configuration layer, but it is inert by
default. It continues work only after the user explicitly invokes the
`phaseharness` skill and that skill creates an active run file.

## Install

Open Claude Code or Codex in the target repository and ask:

```text
Install phaseharness from this installer document:
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

The installer copies `core/.phaseharness/` into the target repository, installs
Claude/Codex `Stop` hook entries, exposes the `phaseharness` skill, generates
provider-native subagent bridge files, and runs smoke verification.

## Run A Task

Use the installed skill explicitly:

```text
Use the phaseharness skill to implement <request> with loop count 2, max attempts per phase 2, and commit mode none.
```

If loop count, max attempts per phase, or commit mode are omitted, the skill
must ask once before it creates an active run. Loop count is the maximum number
of `generate -> evaluate` cycles. Max attempts per phase is the retry budget for
each planned implementation phase. Commit modes are `none`, `final`, and
`phase`.

## Run Options

`loop count` controls how many full build-review cycles a run can make. One
loop means the planned implementation phases run once, then `evaluate` decides
`pass`, `warn`, or `fail`. When `evaluate` fails and queues follow-up phase
files, the next loop returns to `generate`. A loop count of `2` allows one
follow-up build-review cycle after the first evaluation failure.

`max attempts per phase` controls retries inside each executable phase. During
`generate`, it applies separately to every planned implementation phase such as
`phase-001` and `phase-002`. It does not mean the whole workflow restarts.

`commit mode` controls product commits:

- `none`: do not create commits automatically.
- `phase`: commit product changes after each planned implementation phase
  completes.
- `final`: create one product commit after `evaluate` passes or warns.

Commit helpers exclude `.phaseharness/` runtime state and managed provider
bridge files by default.

General questions, short explanations, reviews, and one-off commands do not
activate the loop. Activation requires `.phaseharness/state/active.json` with
`activation_source: "phaseharness_skill"`.

If a conversation is interrupted, invoke the `phaseharness` skill again and ask
it to continue the active run. Resume is explicit so unrelated prompts in a new
session do not restart the loop.

## Where State Lives

All canonical harness files and runtime state live under `.phaseharness/`:

- `.phaseharness/bin/`: state, hook, install, and commit helpers
- `.phaseharness/hooks/`: provider hook wrappers
- `.phaseharness/skills/phaseharness/`: skill instructions
- `.phaseharness/subagents/`: phase-specific subagent instructions
- `.phaseharness/runs/`: per-run artifacts and state
- `.phaseharness/state/`: active run pointer and run index

Provider-required files outside `.phaseharness/` are limited to managed hook
entries, skill symlinks, and provider-native subagent bridge files:

- `.claude/settings.json`
- `.codex/config.toml`
- `.codex/hooks.json` or inline Codex hook config
- `.claude/skills/phaseharness`
- `.agents/skills/phaseharness`
- `.claude/agents/phaseharness-*.md`
- `.codex/agents/phaseharness-*.toml`

## Development

Run local verification:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/.phaseharness/bin/*.py tests/smoke_install.py
```

For implementation details, see `SPEC.md` and `spec/`.
