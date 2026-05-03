# install-harness

Use this document in the target repository session.

You are an agent running at the target repository root. Install the canonical
phaseharness core from this project. This is an installable project: copy the
canonical harness into the target repository and wire provider integrations
from that source.

## 0. Source

The canonical source is:

```text
https://github.com/Ssoon-m/phaseloop
```

By default, install from:

```text
https://github.com/Ssoon-m/phaseloop.git
```

Optional overrides:

- `HARNESS_SOURCE`: absolute path to a local checkout of this repository
- `HARNESS_REPO_URL`: alternate git URL, useful for forks

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

Dirty worktree is allowed, but do not overwrite unrelated user changes.

Phaseharness-owned target paths:

- `.phaseharness/`
- `.claude/settings.json` phaseharness `SessionStart`/`Stop` hook entries and managed permissions
- `.codex/config.toml` `codex_hooks` flag, phaseharness inline hook block, and managed permissions
- `.codex/hooks.json` phaseharness `SessionStart`/`Stop` hook entries
- `.claude/skills/phaseharness`
- `.agents/skills/phaseharness`
- `.claude/agents/phaseharness-*.md`
- `.codex/agents/phaseharness-*.toml`

## 2. Resolve Harness Source

If `HARNESS_SOURCE` is set, verify:

```bash
test -d "$HARNESS_SOURCE/core/.phaseharness"
test -f "$HARNESS_SOURCE/core/.phaseharness/config.toml"
test -f "$HARNESS_SOURCE/core/.phaseharness/bin/phaseharness-hook.py"
test -f "$HARNESS_SOURCE/core/.phaseharness/bin/phaseharness-sync-bridges.py"
test -f "$HARNESS_SOURCE/core/.phaseharness/skills/phaseharness/SKILL.md"
```

If `HARNESS_SOURCE` is not set, clone to a temp directory:

```bash
HARNESS_REPO_URL="${HARNESS_REPO_URL:-https://github.com/Ssoon-m/phaseloop.git}"
HARNESS_SOURCE="$(mktemp -d)/phaseloop"
git clone --depth=1 "$HARNESS_REPO_URL" "$HARNESS_SOURCE"
```

If the checks fail, stop. Do not proceed from a partial source.

## 3. Install Canonical Core

Create the target harness directory and copy the canonical implementation:

```bash
mkdir -p .phaseharness
cp -R "$HARNESS_SOURCE/core/.phaseharness/." .phaseharness/
chmod +x .phaseharness/bin/*.py .phaseharness/hooks/*.sh
```

All phaseharness-owned runtime state, docs, prompts, subagent instructions,
hooks, and scripts must live under `.phaseharness/`.

## 4. Initialize State

Ensure state directories exist:

```bash
mkdir -p .phaseharness/state .phaseharness/runs
```

If `.phaseharness/state/active.json` is missing, create it:

```json
{
  "schema_version": 1,
  "active_run": null,
  "activation_source": null,
  "status": "inactive",
  "session_id": null,
  "provider": null
}
```

If `.phaseharness/state/index.json` is missing, create it:

```json
{
  "schema_version": 1,
  "runs": []
}
```

Do not activate a run during installation. The loop activates only when the user
explicitly invokes the `phaseharness` skill.

## 5. Install SessionStart/Stop Hooks And Skill Bridges

Run:

```bash
python3 .phaseharness/bin/phaseharness-sync-bridges.py
```

This command also creates missing `.phaseharness/state/active.json` and
`.phaseharness/state/index.json` without activating a run.

Expected managed paths:

- `.phaseharness/bin/phaseharness-sync-bridges.py`
- `.claude/settings.json`
- `.codex/config.toml`
- `.codex/hooks.json` unless the target already uses Codex inline hooks only
- `.claude/skills/phaseharness`
- `.agents/skills/phaseharness`
- `.claude/agents/phaseharness-*.md`
- `.codex/agents/phaseharness-*.toml`

The installer generates provider-native subagent bridge files from
`.phaseharness/subagents/`:

- Claude Code project subagents: `.claude/agents/*.md`
- Codex project custom agents: `.codex/agents/*.toml`

The SessionStart hook must only resync provider bridge files from
`.phaseharness/`. It must not create, resume, or advance runs. This keeps
`.phaseharness/subagents/*.md`, `.phaseharness/skills/phaseharness/`, and
`.phaseharness/config.toml` as the SSOT while avoiding loop activation for
normal sessions.

The Stop hook cannot call provider subagent APIs itself because provider hooks
run as shell commands. Instead, the continuation prompt must make the direct
phase-specific subagent call the parent agent's first required action. If
subagent launch is unavailable from the Stop-hook continuation, the parent agent
must not execute the phase locally; it must set the phase to `waiting_user` with
a `subagent_unavailable` error.

The installer must also grant provider permissions from the canonical
`.phaseharness/config.toml` SSOT for the managed phaseharness loop. The config
tables should follow provider-native key names where practical:

- `[permissions.claude.settings.permissions]` maps to `.claude/settings.json`
  `permissions`.
- `[permissions.claude.subagents]` maps to Claude Code subagent frontmatter.
- `[permissions.codex.config]` maps to Codex config/custom-agent keys,
  including `approval_policy`, `sandbox_mode`, and
  `sandbox_workspace_write.*`.

Users may lower these permissions in `.phaseharness/config.toml` after
installation and rerun the bridge sync command if they prefer more approval
prompts.

The installer must preserve user hooks:

- If `.claude/settings.json` already has hooks, keep them and add only the
  phaseharness `SessionStart` and `Stop` hook entries.
- If `.codex/hooks.json` already exists, keep it and add only the phaseharness
  `SessionStart` and `Stop` hook entries.
- If `.codex/config.toml` already uses inline hooks and `.codex/hooks.json` is
  absent, append one managed phaseharness `SessionStart`/`Stop` hook block there.
- If existing hook JSON is invalid, stop and ask the user before editing it.

Codex requires:

```toml
[features]
codex_hooks = true
```

Project-local Codex hooks load only when the project `.codex/` layer is trusted.
Mention this in the final report if Codex is available.

## 6. Activation Contract

The installed Stop hook must be inert for normal questions.

The hook may continue work only when all of these are true:

- `.phaseharness/state/active.json` exists
- `status` is `active`
- `activation_source` is `phaseharness_skill`
- `active_run` points to an existing run directory

The hook must not inspect a normal user prompt and decide to start a run. Run
creation belongs only to the `phaseharness` skill.

If a conversation is interrupted, resume also belongs to the skill. The skill
records a resume request in `.phaseharness/runs/<run-id>/state.json`; the next
Stop hook binds the new provider `session_id` and continues from file state.

## 7. Smoke Verification

Run:

```bash
python3 .phaseharness/bin/phaseharness-state.py --help
python3 .phaseharness/bin/phaseharness-hook.py --help
python3 .phaseharness/bin/phaseharness-sync-bridges.py --help
python3 .phaseharness/bin/commit-result.py --help
python3 -m py_compile .phaseharness/bin/*.py
command -v claude || true
command -v codex || true
```

Optional hook no-op checks:

```bash
printf '{"cwd":"%s","hook_event_name":"SessionStart","source":"startup"}' "$PWD" | .phaseharness/hooks/claude-session-start.sh
printf '{"cwd":"%s","hook_event_name":"SessionStart","source":"startup"}' "$PWD" | .phaseharness/hooks/codex-session-start.sh
printf '{"cwd":"%s","hook_event_name":"Stop","stop_hook_active":false}' "$PWD" | .phaseharness/hooks/claude-stop.sh
printf '{"cwd":"%s","hook_event_name":"Stop","stop_hook_active":false}' "$PWD" | .phaseharness/hooks/codex-stop.sh
```

SessionStart no-op should produce no output. Claude Stop no-op should produce
no output. Codex Stop no-op should produce JSON with `continue: true`.

## 8. Final Report

Use this final report shape. Keep the next step skill-first and copy/pasteable.

````text
Installed phaseharness from:
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md

Created/updated:
- .phaseharness/
- .claude/settings.json phaseharness SessionStart/Stop hook entries
- .codex/config.toml codex_hooks flag
- .codex/hooks.json or inline Codex SessionStart/Stop hook entry
- .claude/skills/phaseharness
- .agents/skills/phaseharness
- .claude/agents/phaseharness-*.md
- .codex/agents/phaseharness-*.toml

Key install details:
- All canonical harness files live under .phaseharness/
- SessionStart hooks silently resync provider bridges from .phaseharness/
- Stop hooks are inert until the phaseharness skill creates an active run
- Provider-native subagent bridge files were generated from .phaseharness/subagents/
- The skill asks for loop count, max attempts per phase, and commit mode before
  creating a run when any value is omitted
- Existing user hooks were preserved
- Smoke verification: <passed or failed>

Next phaseharness prompt to paste:
```text
Use the phaseharness skill to implement <request> with loop count 2, max attempts per phase 2, and commit mode none.
```

Option meanings:
- loop count: maximum number of `generate -> evaluate` build-review cycles.
- max attempts per phase: retry budget for each planned implementation phase,
  not a whole-workflow restart count.
- commit mode:
  - `none`: do not create commits automatically.
  - `phase`: commit product changes after each planned implementation phase.
  - `final`: create one product commit after `evaluate` passes or warns.
````
