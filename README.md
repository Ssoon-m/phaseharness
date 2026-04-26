# phaseloop

Portable phased agent loop for Claude Code and Codex.

This repository defines a provider-neutral harness standard and ships a canonical installable core. The harness is designed around durable files and git state rather than one runtime's conversation memory.

## What It Provides

- Canonical harness core under `core/`
- Installer instructions under `installer/`
- Runtime-neutral contracts under `spec/`
- Claude Code and Codex provider adapters
- Generated bridges for runtime-specific skills and agents

## Repository Layout

```text
.
├── SPEC.md
├── spec/
│   ├── PURPOSE.md
│   ├── CONTRACT.md
│   ├── PROVIDERS.md
│   └── BRIDGES.md
├── installer/
│   └── install-harness.md
├── core/
│   ├── .agent-harness/
│   ├── scripts/
│   └── templates/
└── tests/
    └── smoke_install.py
```

## Install Into A Target Repository

Open an agent session in the target repository and give it `installer/install-harness.md`.

For local testing, provide the source path:

```bash
export HARNESS_SOURCE=/absolute/path/to/phaseloop
```

The installer copies the canonical core, generates runtime bridges, creates project context docs, and runs smoke verification.

## Local Smoke Test

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/scripts/*.py core/.agent-harness/providers/*.py tests/smoke_install.py
```

The smoke test creates a temporary target repository, installs the core, generates Claude/Codex bridges, and verifies script entry points.

## Canonical Paths

- `.agent-harness/skills` is the source of truth for shared skills.
- `.agent-harness/roles` is the source of truth for neutral roles.
- `.claude/`, `.agents/`, and `.codex/` are generated bridge locations in target repositories.

Native subagent files are not the standard. The standard is the file contract plus provider execution contract.
