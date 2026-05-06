# phaseharness

Installable `phaseharness` workflow for Claude Code and Codex.

This repository ships a canonical harness that is copied into a target
repository under `.phaseharness/`. The installed harness uses provider
`SessionStart` hooks to resync bridge files and provider `Stop` hooks plus
durable files to continue a task through:

```text
clarify -> context gather -> plan -> generate -> evaluate
```

The Stop hook is installed at the provider configuration layer, but it is inert
by default. It continues work only after the user explicitly invokes the
`phaseharness` skill and that skill creates an active run file.

## Install

Open Claude Code or Codex in the target repository and ask:

```text
Install phaseharness from this installer document:
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

The installer copies `core/.phaseharness/` into the target repository, installs
Claude/Codex `SessionStart` and `Stop` hook entries, exposes the
`phaseharness` skill, generates provider-native subagent bridge files, and runs
smoke verification.

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

- `.phaseharness/bin/`: state, hook, bridge sync, and commit helpers
- `.phaseharness/hooks/`: provider hook wrappers
- `.phaseharness/skills/phaseharness/`: skill instructions
- `.phaseharness/subagents/`: phase-specific subagent instructions
- `.phaseharness/runs/`: per-run artifacts and state
- `.phaseharness/state/`: active run pointer and run index

Run this command to resync provider bridge files from the `.phaseharness/`
SSOT:

```bash
python3 .phaseharness/bin/phaseharness-sync-bridges.py
```

The installed `SessionStart` hook runs the same bridge sync silently at session
startup/resume, so edits to `.phaseharness/subagents/*.md`,
`.phaseharness/skills/phaseharness/`, or `.phaseharness/config.toml` are
reflected in provider bridge files before the session starts handling prompts.

Provider-required files outside `.phaseharness/` are limited to managed hook
entries, skill symlinks, and provider-native subagent bridge files:

- `.claude/settings.json`
- `.codex/config.toml`
- `.codex/hooks.json`
- `.claude/skills/phaseharness`
- `.agents/skills/phaseharness`
- `.claude/agents/phaseharness-*.md`
- `.codex/agents/phaseharness-*.toml`

## Subagent Behavior

Phaseharness installs provider-native subagent bridge files. Provider hooks run
as shell commands, so they cannot call provider subagent APIs themselves. The
Stop hook returns a continuation prompt whose first required action is a direct
call to the phase-specific subagent:

- Claude Code: `phaseharness-clarify`, `phaseharness-context-gather`,
  `phaseharness-plan`, `phaseharness-generate`, `phaseharness-evaluate`
- Codex: `phaseharness_clarify`, `phaseharness_context_gather`,
  `phaseharness_plan`, `phaseharness_generate`, `phaseharness_evaluate`

The parent conversation must not perform phase work itself. If the provider
cannot invoke the subagent from a Stop-hook continuation, the run is set to
`waiting_user` with a `subagent_unavailable` error instead of falling back to
local execution.

## Permission Behavior

`.phaseharness/config.toml` is the SSOT for managed provider permissions. The
permission tables intentionally mirror provider-native keys where practical:

- `[permissions.claude.settings.permissions]` maps to
  `.claude/settings.json` `permissions`.
- `[permissions.claude.subagents]` maps to Claude Code subagent frontmatter.
- `[permissions.codex.config]` maps to Codex config/custom-agent keys such as
  `approval_policy`, `sandbox_mode`, and `sandbox_workspace_write.*`.

The default profile is broad so each loop phase does not repeatedly stop for
approvals.

These settings are intentionally broad. Install phaseharness only into
repositories where the provider is allowed to edit and run project commands
without repeated approval prompts.
After installation, users may lower these permission settings in
`.phaseharness/config.toml` and rerun the bridge sync command if they prefer
more approval prompts.

## Development

Run local verification:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/.phaseharness/bin/*.py tests/smoke_install.py
```

For implementation details, see `SPEC.md` and `spec/`.
