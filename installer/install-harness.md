# install-harness

Use this document in the target repository session.

You are an agent running at the target repository root. Install the canonical provider-neutral harness from this project. Do not redesign the harness from scratch.

## 0. Source

The canonical phaseloop source is:

```text
https://github.com/Ssoon-m/phaseloop
```

By default, install from:

```text
https://github.com/Ssoon-m/phaseloop.git
```

Optional overrides:

- `HARNESS_SOURCE`: path to a local checkout of phaseloop, useful for local development
- `HARNESS_REPO_URL`: alternate git URL, useful for forks

Do not invent a harness implementation from this installer document. Install from the canonical source or an explicit override.

Local development override:

```bash
export HARNESS_SOURCE=/absolute/path/to/phaseloop
```

Fork override:

```bash
export HARNESS_REPO_URL=<git-url-for-your-fork>
```

## 1. Preflight

Run:

```bash
pwd
git rev-parse --verify HEAD
git status --short
command -v python3
command -v claude || true
command -v codex || true
```

Stop if:

- this is not a git repository
- there is no initial commit
- `python3` is unavailable
- both `claude` and `codex` are unavailable

Dirty worktree is allowed, but do not overwrite unrelated user changes. If a target harness path already exists, inspect it before merging.

Harness-owned target paths:

- `.agent-harness/`
- `.claude/agents/`
- `.claude/skills`
- `.agents/skills`
- `.codex/agents/`
- `scripts/_utils.py`
- `scripts/gen-bridges.py`
- `scripts/gen-docs-diff.py`
- `scripts/run-phases.py`
- `scripts/run-workflow.py`
- `docs/mission.md`
- `docs/spec.md`
- `docs/testing.md`
- `docs/user-intervention.md`
- `tasks/index.json`

## 2. Resolve Harness Source

If `HARNESS_SOURCE` is set, verify:

```bash
test -d "$HARNESS_SOURCE/core"
test -f "$HARNESS_SOURCE/core/.agent-harness/config.toml"
test -f "$HARNESS_SOURCE/core/scripts/run-workflow.py"
```

If `HARNESS_SOURCE` is not set, clone phaseloop to a temp directory:

```bash
HARNESS_REPO_URL="${HARNESS_REPO_URL:-https://github.com/Ssoon-m/phaseloop.git}"
HARNESS_SOURCE="$(mktemp -d)/phaseloop"
git clone --depth=1 "$HARNESS_REPO_URL" "$HARNESS_SOURCE"
```

If the checks fail, stop. Do not proceed from a partial source.

## 3. Install Canonical Core

Create target directories:

```bash
mkdir -p .agent-harness scripts docs tasks
```

Copy or merge the canonical implementation:

```bash
cp -R "$HARNESS_SOURCE/core/.agent-harness/." .agent-harness/
cp "$HARNESS_SOURCE/core/scripts/_utils.py" scripts/
cp "$HARNESS_SOURCE/core/scripts/gen-bridges.py" scripts/
cp "$HARNESS_SOURCE/core/scripts/gen-docs-diff.py" scripts/
cp "$HARNESS_SOURCE/core/scripts/run-phases.py" scripts/
cp "$HARNESS_SOURCE/core/scripts/run-workflow.py" scripts/
```

If any destination already exists and differs, do not blindly overwrite. Read the diff and preserve local project-specific changes unless they are clearly stale generated bridge files.

## 4. Prepare Project Context Docs

The harness expects:

- `docs/mission.md`
- `docs/spec.md`
- `docs/testing.md`
- `docs/user-intervention.md`

For each missing file, start from the template in `$HARNESS_SOURCE/core/templates/docs/`, then adapt it by reading the target repository. Do not leave empty placeholders when repository context is available.

If context is insufficient, write the unknowns explicitly instead of guessing.

## 5. Initialize State

Create `tasks/index.json` if missing:

```json
{
  "tasks": []
}
```

## 6. Configure Providers

Edit `.agent-harness/config.toml` if needed.

Provider selection rules:

- only `claude` available: `default_provider = "claude"`
- only `codex` available: `default_provider = "codex"`
- both available: prefer the current runtime, keep the other as fallback

Headless policy:

- use `AGENT_HEADLESS=1`
- use workspace-write for workflow generation and phase execution
- do not use interactive approval as the headless standard

## 7. Generate Bridges

Run:

```bash
python3 scripts/gen-bridges.py
```

Expected generated paths:

- `.claude/skills` symlink or copy
- `.agents/skills` symlink or copy
- `.claude/agents/phase-{clarify,context,plan,generate,evaluate}.md`
- `.codex/agents/phase-{clarify,context,plan,generate,evaluate}.toml`

These are runtime-specific bridges. The canonical source remains `.agent-harness/skills` and `.agent-harness/roles`.

## 8. Smoke Verification

Run:

```bash
python3 scripts/run-workflow.py --help
python3 scripts/run-phases.py --help
python3 scripts/gen-docs-diff.py --help
python3 scripts/gen-bridges.py --help
python3 -m py_compile scripts/*.py .agent-harness/providers/*.py
command -v claude || true
command -v codex || true
```

Optional explicit work request:

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --max-attempts 2 --session-timeout-sec 600
```

The default runtime strategy is balanced: one analysis agent session for
clarify, context, and plan; build agent session(s) for implementation phases;
and one evaluate agent session for final verification.

## 9. README Note

Do not edit the target repository README by default.

If the user asks how to document the install, include this optional snippet in
the final report instead of applying it automatically:

```markdown
## Agent Harness

This project uses phaseloop. Harness state is stored in `tasks/` and
task artifacts, canonical configuration lives under `.agent-harness/`, and
runtime bridges are generated under `.claude/`, `.agents/`, and `.codex/`.
Headless workflow runs use `AGENT_HEADLESS=1` with balanced
analysis/build/evaluate agent sessions.
```

## 10. Final Report

Report:

- files created or modified
- default provider and fallback provider
- whether bridges are symlink or copy
- smoke verification result
- any docs that still need human clarification
- first command to run

Suggested commit message:

```text
chore(harness): install provider-neutral agent harness

- install canonical .agent-harness core
- add provider adapters and runner scripts
- generate Claude/Codex bridges
- add harness docs and task state
```
