---
name: phaseharness
description: Use only when the user explicitly invokes phaseharness or asks to start/resume the phaseharness workflow. Runs clarify -> context-gather -> plan -> generate -> evaluate from durable .phaseharness run files.
---

# Phaseharness

Phaseharness runs a large repository task from durable file state under `.phaseharness/runs/<run-id>/`.

Workflow:

```text
clarify -> context_gather -> plan -> generate -> evaluate
```

## Start Or Resume

1. Summarize the task in one sentence.
2. Sync provider bridges:

```bash
python3 .phaseharness/bin/phaseharness-sync-bridges.py
```

3. Check active state:

```bash
python3 .phaseharness/bin/phaseharness-state.py status --json
```

4. Before creating a new auto run, ask for:

- loop count: maximum number of `generate -> evaluate` cycles
- commit mode: `none`, `phase`, or `final`

Use these defaults only after the user accepts them:

- loop count: `2`
- commit mode: `none`

Ask in Korean when values are missing:

```text
Phaseharness 실행 옵션을 먼저 확인할게요.

- loop count: evaluate가 fail일 때 generate -> evaluate를 다시 돌릴 수 있는 최대 횟수입니다. 기본값: 2
- commit mode: 기본값 none
  - none: commit prompt를 만들지 않습니다.
  - phase: 각 generate phase 완료 후 `commit`으로 커밋합니다.
  - final: evaluate pass/warn 후 `commit`으로 한 번 커밋합니다.

기본값으로 진행할까요? 또는 `loop count 3, commit mode final`처럼 지정해주세요.
```

5. Create the run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode auto --request "<request>" --loop-count <count> --commit-mode <none|phase|final> --json
```

6. Get and execute the first continuation prompt:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
```

If the result action is `prompt`, execute that prompt in the main session. Do not wait for the Stop hook when starting inside the current turn.

## Auto Mode

- Only runs created by `phaseharness` with `mode: auto` are eligible for Stop-hook continuation.
- Stop hooks call only:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --json
```

- Stop hooks do not run LLMs, subagents, product code edits, evaluation, or git commits.
- If a stage remains `running`, `next --reprompt-running` returns a re-entry prompt for the same stage instead of starting a duplicate stage.

## Manual Skills

- `clarify`, `context-gather`, `plan`, `generate`, and `evaluate` can be run directly.
- Direct skill runs perform one stage and stop.
- Manual runs do not activate Stop-hook continuation.
- If the user later says "modify based on that", treat it as a normal direct implementation request unless they explicitly invoke `generate` with a phase file.

## Stage Responsibilities

- `clarify`, `context-gather`, and `plan` are performed by the main session.
- `generate` and `evaluate` are controller-led in the main session and delegated to one fresh subagent.
- Subagents do not call state commands, change run lifecycle, or commit.
- The main session writes artifacts, updates state, and handles commit prompts with `commit`.

## Commit Modes

- `none`: no commit prompt.
- `phase`: after each generated phase completes, the state runner returns a commit prompt.
- `final`: after evaluate is `pass` or `warn`, the state runner returns a final commit prompt.
- Commit prompts include run id, commit key, commit mode, eligible paths, skipped baseline paths, runtime/bridge skips, and `set-commit` follow-up commands.
- The state runner never runs `git commit`.
