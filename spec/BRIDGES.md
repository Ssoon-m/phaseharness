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

Automation may call these roles as isolated provider sessions. Runtime bridges
also expose them as native subagents for interactive Claude/Codex use.

## Role Metadata

`role.toml` includes:

```toml
name = "phase-clarify"
description = "Clarifies a requested task into a concrete goal, non-goals, assumptions, and done conditions."
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
