# Bridges

Phaseharness keeps canonical files under `.phaseharness/`.

Provider-required bridge files outside that directory are minimal:

- `.claude/settings.json`: project `Stop` hook entry
- `.codex/config.toml`: `codex_hooks = true`
- `.codex/hooks.json` or inline Codex hook entry
- `.claude/skills/phaseharness`: symlink or copy to the canonical skill
- `.agents/skills/phaseharness`: symlink or copy to the canonical skill
- `.claude/agents/phaseharness-*.md`: Claude Code project subagents generated from canonical subagent prompts
- `.codex/agents/phaseharness-*.toml`: Codex project custom agents generated from canonical subagent prompts

Provider-native subagent bridge files are generated from `.phaseharness/subagents/`.
They are bridge/config artifacts, not canonical source.

## Hook Merge Rules

The install helper must:

- preserve existing user hooks
- add or replace only entries whose command contains `phaseharness-hook.py`
- preserve existing Codex inline hooks when no `hooks.json` exists
- enable `codex_hooks = true`
- stop on invalid JSON instead of guessing

## Skill Bridge

The canonical skill lives at:

```text
.phaseharness/skills/phaseharness/SKILL.md
```

Runtime skill bridge targets:

```text
.claude/skills/phaseharness
.agents/skills/phaseharness
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

The installer rewrites these bridge files from the canonical prompts.

The Stop hook does not invoke provider subagent APIs directly because hooks run
as shell commands. Each continuation prompt makes the matching provider
subagent call the parent agent's first required action:

- Claude Code subagents use hyphenated names such as
  `phaseharness-context-gather`.
- Codex custom agents use underscored names such as
  `phaseharness_context_gather`.
- If the provider does not launch the subagent, the parent agent must not
  execute the phase locally. It records `subagent_unavailable` and sets the
  phase to `waiting_user`.
