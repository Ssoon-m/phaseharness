---
name: phaseharness
description: Use only when the user explicitly asks to use the phaseharness skill for a repository task.
---

# Phaseharness

Use this skill only when the user explicitly asks to use `phaseharness`.
Do not use it for ordinary questions, short explanations, reviews, or one-off
commands.

Phaseharness runs one concrete repository task through this fixed workflow:

```text
clarify -> context gather -> plan -> generate -> evaluate
```

`loop_count` is the maximum number of `generate -> evaluate` cycles. If
`evaluate` fails and creates follow-up implementation phases, the `Stop` hook
may enter the next loop until this budget is exhausted.

`max_attempts_per_phase` is the retry budget for each executable phase prompt,
including each planned implementation phase such as `phase-001`.

The loop is driven by `Stop` hooks and file state under `.phaseharness/`. The
hook is installed globally for the project, but it is normally inert. It may
continue work only when `.phaseharness/state/active.json` contains an active run
with `activation_source: "phaseharness_skill"`.

## Start A Run

1. Identify the concrete user request.
2. Check whether an active or resumable run already exists:

```bash
python3 .phaseharness/bin/phaseharness-state.py status --json
```

3. If a run is active and the user wants to continue it, do not create a new
   run. Request resume instead:

```bash
python3 .phaseharness/bin/phaseharness-state.py resume --summary "<what the user asked to continue>"
```

Then stop normally. The `Stop` hook will attach the current provider session and
continue from file state.

4. For a new run, determine `loop_count` before starting.
   - If the user already specified it, use that positive integer.
   - If not, ask once: `How many generate/evaluate loops should this run allow? Default is 2.`
   - Do not start until the user chooses a number or explicitly accepts the
     default.
5. Determine `max_attempts_per_phase` before starting.
   - If the user already specified it, use that positive integer.
   - If not, ask once: `How many attempts should each implementation phase get? Default is 2.`
   - Do not start until the user chooses a number or explicitly accepts the
     default.
6. Determine `commit_mode` before starting.
   - If the user already specified `none`, `final`, or `phase`, use that value.
   - If not, ask once: `Commit mode for this phaseharness task? none, final, or phase. Default is none.`
   - `none`: do not create product commits automatically.
   - `final`: create one product commit after `evaluate` passes or warns.
   - `phase`: create a product commit after each planned implementation phase completes.
   - Do not start until the user chooses a mode or explicitly accepts the
     default.
7. If any value is missing, ask using this exact style. Do not show only raw
   variable names:

```text
phaseharness 실행 옵션을 정해야 합니다. 기본값으로 시작해도 되고, 원하는 값만 바꿔서 답해도 됩니다.

- loop count: generate -> evaluate 전체 사이클을 몇 번까지 허용할지 정합니다. evaluate가 실패하고 후속 phase가 생기면 다음 loop로 돌아갑니다. 기본값: 2
- max attempts per phase: plan에서 나뉜 각 implementation phase를 실패 시 몇 번까지 다시 시도할지 정합니다. 전체 workflow 반복 횟수가 아닙니다. 기본값: 2
- commit mode: 자동 commit 방식입니다. 기본값: none
  - none: 자동 commit을 만들지 않습니다.
  - phase: 각 implementation phase가 완료될 때마다 product change를 commit합니다.
  - final: 최종 evaluate가 pass 또는 warn이면 product commit 하나를 만듭니다.

기본값으로 진행할까요?
원하면 `loop count 3, max attempts per phase 2, commit mode final`처럼 답해주세요.
```

8. Create an active run:

```bash
python3 .phaseharness/bin/phaseharness-state.py start --request "<request>" --loop-count <loops> --max-attempts-per-phase <attempts> --commit-mode <mode>
```

9. Use the printed run id as `<run-id>`.
10. Do not perform `clarify` in the current conversation.
11. Stop normally. The project `Stop` hook will read the active run and continue
   with `clarify` through the provider-native phaseharness subagent when
   supported.

## State Rules

- Never create or activate a run unless the user explicitly invoked
  `phaseharness`.
- Never infer activation from ordinary prompts.
- If a previous run is active in another session, resume only after the user
  explicitly asks phaseharness to continue it.
- New sessions must rebuild context from `.phaseharness/runs/<run-id>/state.json`
  and artifacts, not from previous conversation memory.
- Every phase must read previous artifacts from disk.
- Every phase must write its required artifact before marking itself completed.
- Every phase must update `.phaseharness/runs/<run-id>/state.json` before ending
  the turn.
- `plan` must create one or more `.phaseharness/runs/<run-id>/phases/phase-NNN.md`
  implementation phase files.
- `generate` must complete only the current implementation phase named in the
  continuation prompt. It must update `state.generate.phase_status`, not mark
  top-level `generate` completed.
- `evaluate` may create follow-up implementation phase files on `fail`; the
  Stop hook will loop back to `generate` only while `loop.current < loop.max`.
- If user input is required, set run `status` to `waiting_user`, set
  `needs_user` to `true`, write the question into the current artifact, and
  ask the user. The Stop hook will not continue while waiting.
- Commit modes exclude `.phaseharness/` runtime files and managed provider
  hook/skill bridge files from product commits.
- Do not push.

## Artifact Paths

- `clarify`: `.phaseharness/runs/<run-id>/artifacts/01-clarify.md`
- `context_gather`: `.phaseharness/runs/<run-id>/artifacts/02-context.md`
- `plan`: `.phaseharness/runs/<run-id>/artifacts/03-plan.md`
- `generate`: `.phaseharness/runs/<run-id>/artifacts/04-generate.md`
- `evaluate`: `.phaseharness/runs/<run-id>/artifacts/05-evaluate.md`

## Completion

When `evaluate` is complete:

- Write `artifacts/05-evaluate.md`.
- Set `evaluation.status` to `pass`, `warn`, or `fail`.
- If `pass` or `warn`, set `evaluate` phase to `completed`.
- If `fail` and fixable, add follow-up `phases/phase-NNN.md` files before
  marking `evaluate` completed.
- Stop normally. The Stop hook will mark the run completed and deactivate
  `.phaseharness/state/active.json`.

For a manual product commit after a completed run:

```bash
python3 .phaseharness/bin/commit-result.py <run-id>
```
