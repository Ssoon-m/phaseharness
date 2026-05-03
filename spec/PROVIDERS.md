# Providers

Phaseharness uses provider lifecycle hooks and provider-native subagent bridge
files.

## Claude Code

Claude Code uses a project `Stop` hook entry in `.claude/settings.json`.

Continuation output:

```json
{
  "decision": "block",
  "reason": "<next phase prompt>"
}
```

No-op output is empty stdout.

## Codex

Codex uses project hooks from `.codex/hooks.json` or inline `.codex/config.toml`.
The installer must set:

```toml
[features]
codex_hooks = true
```

Codex project hooks load only when the project config layer is trusted.

Continuation output:

```json
{
  "decision": "block",
  "reason": "<next phase prompt>"
}
```

No-op output:

```json
{
  "continue": true
}
```

## Shared Rules

- Hooks must read file state before continuing.
- Hooks must not create active runs.
- Hooks must not continue while `needs_user` is true.
- Hooks must not continue in a different provider session unless the
  `phaseharness` skill requested resume in file state.
- Hooks must respect `max_attempts_per_phase` budgets. The budget is checked
  whenever a `Stop` hook sees the current implementation phase or executable
  phase prompt still `running` or retryable after an agent turn.
- Hooks must respect `loop_count`: an `evaluate` failure may return to
  `generate` only when a pending follow-up implementation phase exists and
  `loop.current < loop.max`.
- Hooks must respect `commit_mode`: `none` never commits, `phase` commits
  product changes after each implementation phase, and `final` commits product
  changes after a pass/warn `evaluate`.
