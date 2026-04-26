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

## Role Metadata

`role.toml` includes:

```toml
name = "tech-critic-lead"
description = "Critical reviewer that approves, rejects, or requests revision for implementation plans."
model_tier = "strong"
sandbox_mode = "read-only"
tools_policy = "read-only"
output_schema = "decision_v1"
```

The exact runtime model name is chosen by the provider bridge. `model_tier` is intentionally abstract.

## Role Output

Role output is stored as JSON:

```json
{
  "role": "tech-critic-lead",
  "decision": "approve",
  "reasons": [],
  "required_changes": [],
  "human_intervention_required": false
}
```

Allowed decisions:

- `approve`
- `revise`
- `reject`

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
name: tech-critic-lead
description: Critical reviewer...
tools: Read, Grep, Glob, Bash
model: inherit
---

...
```

## Codex Bridge Mapping

Codex custom agents are TOML files:

```toml
name = "tech_critic_lead"
description = "Critical reviewer..."
sandbox_mode = "read-only"
developer_instructions = """
...
"""
```

Hyphenated role names may be converted to underscores for Codex agent names when needed, but the canonical role name remains unchanged.
