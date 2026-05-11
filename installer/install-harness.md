# install-harness

Use this document in the target repository session.

Install Phaseharness into another repository. The files to copy are stored in this repository's `.phaseharness/` directory.

## Source

Default repository:

```text
https://github.com/Ssoon-m/phaseharness.git
```

Optional overrides:

- `HARNESS_SOURCE`: absolute path to a local checkout of this repository
- `HARNESS_REPO_URL`: alternate git URL

## Preflight

Run from the target repository root:

```bash
pwd
git rev-parse --verify HEAD
git status --short
command -v python3
```

Stop if this is not a git repository, there is no initial commit, or `python3` is unavailable. Dirty worktree is allowed, but do not overwrite unrelated user changes.

## Resolve The Source Repository

If `HARNESS_SOURCE` is set:

```bash
test -d "$HARNESS_SOURCE/.phaseharness"
test -f "$HARNESS_SOURCE/.phaseharness/bin/phaseharness-state.py"
test -f "$HARNESS_SOURCE/.phaseharness/bin/phaseharness-hook.py"
test -f "$HARNESS_SOURCE/.phaseharness/bin/phaseharness-sync-bridges.py"
test -f "$HARNESS_SOURCE/.phaseharness/skills/phaseharness/SKILL.md"
test -f "$HARNESS_SOURCE/.phaseharness/skills/commit/SKILL.md"
```

If `HARNESS_SOURCE` is not set:

```bash
HARNESS_REPO_URL="${HARNESS_REPO_URL:-https://github.com/Ssoon-m/phaseharness.git}"
HARNESS_SOURCE="$(mktemp -d)/phaseharness"
git clone --depth=1 "$HARNESS_REPO_URL" "$HARNESS_SOURCE"
```

## Copy Phaseharness Files

```bash
mkdir -p .phaseharness
cp -R "$HARNESS_SOURCE/.phaseharness/." .phaseharness/
chmod +x .phaseharness/bin/*.py .phaseharness/hooks/*.sh
```

All installed workflow files live under `.phaseharness/`.

## Connect Tool Files

```bash
python3 .phaseharness/bin/phaseharness-sync-bridges.py
```

This creates or updates:

- `.claude/settings.json` phaseharness `SessionStart` and `Stop` hook entries
- `.codex/config.toml` `[features].hooks = true`
- `.codex/hooks.json` phaseharness `SessionStart` and `Stop` hook entries
- `.claude/skills/{clarify,context-gather,plan,generate,evaluate,commit,phaseharness}`
- `.agents/skills/{clarify,context-gather,plan,generate,evaluate,commit,phaseharness}`
- `.phaseharness/state/active.json`
- `.phaseharness/state/index.json`

Subagents are not predeclared. The `generate` and `evaluate` skills create fresh subagent requests when those stages run.

## When The Stop Hook Runs

The installed Stop hook is inert for normal questions. It only calls:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
```

The hook may continue work only when `.phaseharness/state/active.json` points to an active auto run created by `phaseharness`.

## Smoke Verification

```bash
python3 .phaseharness/bin/phaseharness-state.py --help
python3 .phaseharness/bin/phaseharness-hook.py --help
python3 .phaseharness/bin/phaseharness-sync-bridges.py --help
python3 -m py_compile .phaseharness/bin/*.py
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
```

When no automatic run is active, the output should include `"action": "none"`.
