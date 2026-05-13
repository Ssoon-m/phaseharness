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

4. If an active run exists in this worktree, do not create a new run and do not automatically resume. Ask the user to choose:

- `resume`: bind the existing active run to the current session and continue it.
- `start-new`: pause the existing active run, clear this worktree's active slot, and start the current request as a new run in this same worktree.
- `start-new-in-worktree`: keep the existing run active here, then create a new git worktree and branch for a separate phaseharness run.

Use this Korean prompt:

```text
이 worktree에 active phaseharness run이 있습니다.

- resume: 기존 run을 현재 세션에 바인딩하고 이어갑니다.
- start-new: 기존 run을 pause로 주차하고, 지금 요청한 작업을 이 worktree에서 새 run으로 시작합니다.
- start-new-in-worktree: 기존 run은 그대로 두고, 새 git worktree/branch에서 별도 run을 시작합니다.

어떻게 진행할까요?
```

If the user chooses `resume`, run:

```bash
python3 .phaseharness/bin/phaseharness-state.py resume --json
```

Then continue with step 7.

If the user chooses `start-new`, continue to step 5. In step 6, create the new run with:

```bash
python3 .phaseharness/bin/phaseharness-state.py start-new --request "<request>" --loop-count <count> --commit-mode <none|phase|final> --json
```

This command validates the new run, parks the existing active run with `manual_pause`, clears this worktree's active slot, and creates the new active run. It only updates `.phaseharness` run state. It does not clean the working tree, reset files, or clear git staging. If file isolation is needed, use `start-new-in-worktree` instead.

If the user chooses `start-new-in-worktree`, first confirm loop count and commit mode using the same defaults from step 5 when values are missing. Then run:

```bash
python3 .phaseharness/bin/phaseharness-worktree.py create --request "<request>" --loop-count <count> --commit-mode <none|phase|final> --json
```

This creates the git worktree and also creates an unbound auto run under the new worktree's `.phaseharness/runs/<run-id>/`. It must not change the current worktree's active run.

Tell the user the worktree path, harness path, branch, and run id. Tell them to start a new Codex/Claude session with cwd set to the returned harness path, then run:

```bash
python3 .phaseharness/bin/phaseharness-state.py resume --json
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

Do not run those handoff commands in the current session. The current session remains bound to the original worktree. Do not bind a second run to the current session and do not ask the user to repeat the original request.

5. Before creating a new auto run, ask for:

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

6. Create the run. Auto runs bind to the current provider session. If the runner cannot infer the session id, stop and report the error instead of creating an unbound auto run. If `start-new` was selected, use the `start-new` command shown above instead of this command:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --mode auto --request "<request>" --loop-count <count> --commit-mode <none|phase|final> --json
```

7. Get and execute the first continuation prompt:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

If the result action is `prompt`, execute that prompt in the main session. Do not wait for the Stop hook when starting inside the current turn.

## Auto Mode

- Only runs created by `phaseharness` with `mode: auto` are eligible for Stop-hook continuation.
- Stop hooks call only:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

- Stop hooks do not run LLMs, subagents, product code edits, evaluation, or git commits.
- Stop hooks continue only when the hook session id matches the run's bound session id. Missing session id or missing binding is a no-op.
- If a stage remains `running`, `next --reprompt-running` returns a re-entry prompt for the same stage instead of starting a duplicate stage.

## Parallel Worktrees

- One worktree has at most one active phaseharness run.
- Parallel phaseharness work must use `phaseharness-worktree.py create`, which creates:
  - run/worktree name: `YYYYMMDD-HHMMSS-<task-slug>`
  - branch: `phaseharness/<name>`
  - path: `<repo-parent>/<repo-name>.worktrees/<name>`
  - an unbound auto run under the new worktree's `.phaseharness/runs/<run-id>/`
- Start a new session whose cwd is the returned harness path, run `resume`, then run `next`.

## Manual Skills

- `clarify`, `context-gather`, `plan`, `generate`, and `evaluate` can be run directly.
- Direct skill runs perform one stage and stop.
- Manual runs do not activate Stop-hook continuation.
- If the user later says "modify based on that", treat it as a normal direct implementation request unless they explicitly invoke `generate` with a phase file.

## Stage Responsibilities

- `clarify`, `context-gather`, and `plan` are performed by the main session.
- `generate` and `evaluate` are controller-led in the main session and delegated to one fresh subagent.
- An explicit user request to pause or stop the run is handled with `pause` at any stage.
- Only `clarify` may pause for missing user input with `wait-user`; later stages must proceed with documented assumptions, risks, blockers, or an error state.
- Subagents do not call state commands, change run lifecycle, or commit.
- The main session writes artifacts, updates state, and handles commit prompts with `commit`.

## Commit Modes

- `none`: no commit prompt.
- `phase`: after each generated phase completes, the state runner returns a commit prompt.
- `final`: after evaluate is `pass` or `warn`, the state runner returns a final commit prompt.
- Commit prompts include run id, commit key, commit mode, eligible paths, skipped baseline paths, runtime/bridge skips, and `set-commit` follow-up commands.
- Unsafe or ambiguous commit prompts are recorded as `skipped` and do not pause the workflow.
- The state runner never runs `git commit`.
