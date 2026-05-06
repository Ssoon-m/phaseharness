# Bridges

Phaseharness keeps canonical files under `.phaseharness/`.

Provider-required bridge files outside that directory are limited to runtime
integration, permission, and bridge files:

- `.claude/settings.json`: project `SessionStart`/`Stop` hook entries and phaseharness
  permission settings
- `.codex/config.toml`: `codex_hooks = true` and phaseharness permission
  settings
- `.codex/hooks.json`: Codex `SessionStart`/`Stop` hook entries
- `.claude/skills/phaseharness`: symlink or copy to the canonical skill
- `.claude/skills/commit`: symlink or copy to the canonical skill
- `.agents/skills/phaseharness`: symlink or copy to the canonical skill
- `.agents/skills/commit`: symlink or copy to the canonical skill
- `.claude/agents/phaseharness-*.md`: Claude Code project subagents generated from canonical subagent prompts
- `.codex/agents/phaseharness-*.toml`: Codex project custom agents generated from canonical subagent prompts

Provider-native subagent bridge files are generated from `.phaseharness/subagents/`.
They are bridge/config artifacts, not canonical source.

`.phaseharness/bin/phaseharness-sync-bridges.py` is the primary bridge sync entrypoint.
It reads `.phaseharness/config.toml`, `.phaseharness/subagents/`, and
`.phaseharness/skills/`, then regenerates provider bridge files.

## Hook Merge Rules

The bridge sync command must:

- preserve existing user hooks
- add or replace only entries whose command contains `.phaseharness`
- always install Codex phaseharness hooks in `.codex/hooks.json`
- remove previous phaseharness managed Codex inline hook blocks from
  `.codex/config.toml`
- preserve unrelated user-authored `.codex/config.toml` content
- enable `codex_hooks = true`
- stop on invalid JSON instead of guessing
- install `SessionStart` only for bridge sync; install `Stop` only for workflow
  continuation

## Skill Bridges

Canonical skills live under:

```text
.phaseharness/skills/<skill-name>/SKILL.md
```

Runtime skill bridge targets:

```text
.claude/skills/phaseharness
.claude/skills/commit
.agents/skills/phaseharness
.agents/skills/commit
```

Symlinks are preferred. Copies are acceptable when symlinks are unavailable.

## Subagent Bridges

Canonical subagent prompts live at:

```text
.phaseharness/subagents/*.md
```

Runtime provider bridge targets:

```text
.claude/agents/phaseharness-*.md
.codex/agents/phaseharness-*.toml
```

The bridge sync command rewrites these bridge files from the canonical prompts.

The SessionStart hook silently regenerates provider-native bridge files from the
canonical prompts. The Stop hook does not invoke provider subagent APIs directly
because hooks run as shell commands. Each continuation prompt makes the matching
provider subagent call the parent agent's first required action:

- Claude Code subagents use hyphenated names such as
  `phaseharness-context-gather`.
- Codex custom agents use underscored names such as
  `phaseharness_context_gather`.
- If the provider does not launch the subagent, the parent agent must not
  execute the phase locally. It records `subagent_unavailable` and sets the
  phase to `waiting_user`.

## Permission Bridges

`.phaseharness/config.toml` is the SSOT for managed permissions. Permission
tables follow provider-native key names where practical:

- `[permissions.claude.settings.permissions]` maps to `.claude/settings.json`
  `permissions`.
- `[permissions.claude.subagents]` maps to Claude Code subagent frontmatter.
- `[permissions.claude.phaseharness]` contains phaseharness-only bridge controls
  such as `allowManagedSubagents`.
- `[permissions.codex.config]` maps to Codex config/custom-agent keys,
  including `approval_policy`, `sandbox_mode`, and
  `sandbox_workspace_write.*`.
