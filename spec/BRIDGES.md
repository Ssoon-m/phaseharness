# Bridges

Bridges expose canonical harness assets to runtime-specific discovery paths.

The canonical source always lives under `.agent-harness/`. Runtime-specific directories are generated or linked artifacts.

## Skills

Canonical source:

```text
.agent-harness/skills/
```

Runtime bridges:

```text
.claude/skills -> ../.agent-harness/skills
.agents/skills -> ../.agent-harness/skills
```

If symlinks are unavailable or undesirable, installer may create generated copies instead. Generated copies must be treated as disposable bridge output.

## Roles

Canonical role source:

```text
.agent-harness/roles/<role-name>/
  role.toml
  prompt.md
```

Generated runtime bridges:

```text
.claude/agents/<role-name>.md
.codex/agents/<role-name>.toml
```

The role source contains runtime-neutral metadata and instructions. The generated bridge adapts that source to each runtime's file format.

Canonical workflow roles:

- `phase-clarify`
- `phase-context`
- `phase-plan`
- `phase-generate`
- `phase-evaluate`

Automation may call context, plan, generate, and evaluate roles as isolated
headless agent sessions. The clarify role is a main-session guide and artifact
contract, not a default headless phase. Runtime bridges also expose roles as
native subagents for interactive Claude/Codex use.

In the default balanced workflow, the orchestrator combines
`phase-context` and `phase-plan` into one analysis agent session after
main-session clarify writes the first artifact. The roles remain separate
canonical prompt assets so the contract stays readable and bridgeable even when
a session executes more than one logical role.

## Role Metadata

`role.toml` includes:

```toml
name = "phase-clarify"
description = "Guides main-session clarification into concrete questions, user decisions, scope, and done conditions."
sandbox_mode = "read-only"
tools_policy = "read-only"
```

The exact runtime model name is chosen by the provider bridge when a runtime supports role-specific model selection.

## Bridge Generation Rules

`scripts/gen-bridges.py` is responsible for bridge generation.

Required behavior:

- Create `.claude/agents/*.md` from role metadata and prompt.
- Create `.codex/agents/*.toml` from role metadata and prompt.
- Create skill symlinks when safe.
- Fall back to generated skill copies when symlinks fail and copy mode is requested.
- Never treat generated bridge files as canonical source.

## Bridge Sync Hooks

The common bridge sync implementation is:

```text
scripts/sync-bridges.py
```

Runtime hook adapters call that common script:

```text
.claude/hooks/phaseloop-sync-bridges.sh
.codex/hooks/phaseloop-sync-bridges.sh
```

`scripts/install-hooks.py` installs the adapters and merges runtime hook
configuration. It must be idempotent and must preserve user hooks.

Merge rules:

- Do not overwrite `.claude/settings.json`.
- Do not overwrite `.codex/hooks.json`.
- Do not overwrite `.codex/config.toml`.
- Add or replace only hook entries whose command contains `phaseloop-sync-bridges`.
- If Codex already has `.codex/hooks.json`, merge phaseloop into that file.
- If Codex only has inline hooks in `.codex/config.toml`, append one managed
  phaseloop block there.
- If both Codex hook forms already exist, do not create a new representation;
  merge into `.codex/hooks.json`.
- If existing hook JSON is invalid, stop instead of guessing.

The sync hook fingerprints `.agent-harness/` and runs
`scripts/gen-bridges.py` when canonical harness files change. The fingerprint
state is stored in `.agent-harness/.bridge-sync-state.json`, which is ignored by
`.agent-harness/.gitignore`.

## Claude Bridge Mapping

Claude agent files are Markdown with YAML frontmatter:

```markdown
---
name: phase-clarify
description: Clarifies a requested task...
tools: Read, Grep, Glob, Bash
model: inherit
---

...
```

## Codex Bridge Mapping

Codex custom agents are TOML files:

```toml
name = "phase_clarify"
description = "Clarifies a requested task..."
sandbox_mode = "read-only"
developer_instructions = """
...
"""
```

Hyphenated role names may be converted to underscores for Codex agent names when needed, but the canonical role name remains unchanged.
