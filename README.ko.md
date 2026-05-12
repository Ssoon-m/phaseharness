# Phaseharness

Phaseharness는 큰 AI 코딩 작업을 파일 기반 단계로 나누어 진행하는 workflow 시스템입니다.

phaseharness 스킬 사용시 작업은 아래 순서로 진행됩니다.

```text
clarify -> context_gather -> plan -> generate -> evaluate
```

대화 기록에 의존하지 않고, 각 작업의 진행 기록을 파일로 남깁니다.

```text
.phaseharness/runs/<run-id>/
```

이 구조로 인해 긴 작업을 중간에 멈췄다가 다시 이어가거나, 현재 상태를 검토하거나, 중복 실행을 피하기 쉽습니다.

## 무엇을 하는가

Phaseharness는 작업을 아래처럼 나눕니다.

- 요구사항을 명확히 정리합니다.
- 저장소 구조와 관련 파일을 조사합니다.
- 독립적으로 구현 가능한 phase 파일을 만듭니다.
- phase 하나씩 구현합니다.
- 현재 diff가 합의한 기준을 만족하는지 평가합니다.

Python 상태 관리 스크립트는 상태 파일을 읽고 쓰며 다음 prompt를 출력할 뿐입니다. 모델을 실행하거나, subagent를 만들거나, 실제 코드를 수정하거나, 결과를 평가하거나, `git commit`을 실행하지 않습니다.

## phaseharness 시작하기

Phaseharness를 설치할 저장소에서 사용 중인 agent를 실행시켜 아래 문장을 입력하세요.

```text
Install phaseharness from this installer document:
https://github.com/Ssoon-m/phaseharness/blob/main/installer/install-harness.md
```

## 빠른 시작

agent에게 workflow skill 사용을 요청합니다.

```text
Use `phaseharness` to implement <task>.
```

run을 만들기 전에 `phaseharness`는 먼저 현재 worktree에 active run이 있는지 확인합니다. active run이 있으면 아래 중 하나를 선택하게 합니다.

- `resume`: 기존 active run을 현재 session에 바인딩하고 이어갑니다.
- `start-new-in-worktree`: 새 git worktree와 branch를 만들고 별도 run을 시작하게 합니다.
- `cancel`: 아무것도 하지 않습니다.

active run이 없으면 `phaseharness`는 아래 옵션을 확인합니다.

- `loop count`: `generate -> evaluate` cycle 최대 횟수
- `commit mode`: `none`, `phase`, `final` 중 하나

기본값은 아래와 같습니다.

```text
loop count: 2
commit mode: none
```

확인이 끝나면 `phaseharness`가 run을 만들고, 현재 provider session에 바인딩한 뒤 run 파일 기준으로 첫 단계를 시작합니다.

## 병렬 run

하나의 worktree에는 active phaseharness run을 하나만 둡니다. 병렬 phaseharness 작업은 같은 working tree에 여러 active run을 두는 방식이 아니라 git worktree로 분리합니다.

```bash
python3 .phaseharness/bin/phaseharness-worktree.py create --request "<request>" --json
```

기본 naming 규칙은 아래와 같습니다.

- run/worktree name: `YYYYMMDD-HHMMSS-<task-slug>`
- branch: `phaseharness/<name>`
- path: `<repo-parent>/<repo-name>.worktrees/<name>`

새 run은 새 worktree에서 새 Codex/Claude session을 열고 시작하며, run을 만들 때 반환된 `run_id`를 사용합니다.

## 수동 skill

각 단계를 직접 실행할 수도 있습니다.

- `clarify`: 요구사항, 성공 기준, 범위, 제외 범위, 가정, 열린 질문을 정리합니다.
- `context-gather`: 저장소 구조, 관련 파일, 기존 패턴, 제약, 리스크, 검증 명령을 수집합니다.
- `plan`: `artifacts/plan.md`와 자기완결적인 `phases/phase-NNN.md` 파일을 만듭니다. 기능 단위, 오래 걸리는 작업, 검증 기준이 다른 작업, 위험도가 다른 작업은 별도 phase로 나눕니다.
- `generate`: 이미 존재하는 phase 파일 하나만 구현합니다. 일반 구현 명령으로 쓰지 않습니다.
- `evaluate`: 현재 diff가 작업 기준을 만족하는지 검증합니다.
- `commit`: 사용자가 명시적으로 요청했거나 Phaseharness가 commit prompt를 만들었을 때 의미 있는 commit을 만듭니다.

수동 skill 실행은 한 단계만 수행하고 멈춥니다. Stop hook으로 다음 단계가 자동 진행되지 않습니다.

## Phase 분리 기준

`plan`은 phase 수를 줄이는 것보다 독립 구현과 독립 검증이 가능한지를 우선합니다.

phase를 나누는 기준은 아래와 같습니다.

- 사용자에게 보이는 기능이나 동작이 독립적으로 완성될 수 있으면 별도 phase로 나눕니다.
- 작업이 오래 걸리거나 많은 파일을 건드릴 가능성이 있으면 더 작은 phase로 나눕니다.
- 데이터 구조, 상태 처리, UI 동작, 외부 연동, 테스트 기반처럼 위험도가 다른 작업은 분리합니다.
- 검증 명령이나 acceptance criteria가 다르면 분리합니다.
- 이후 작업의 불확실성을 줄이는 준비 작업은 별도 phase로 둘 수 있습니다.
- target files, allowed changes, forbidden changes가 너무 넓어지면 phase를 더 쪼갭니다.

반대로 단순히 파일별로 나누는 것은 피합니다. 각 phase는 fresh implementer가 대화 기억 없이 구현할 수 있고, fresh reviewer가 phase 파일과 diff만 보고 검증할 수 있어야 합니다.

## 자동 run

자동 run은 `phaseharness`만 만듭니다. Stop hook은 자동 run만 이어갈 수 있습니다.

Stop hook이 호출하는 명령은 아래 하나뿐입니다.

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

Stop hook은 모델을 실행하지 않고, subagent를 만들지 않고, 파일을 수정하지 않고, 평가하지 않고, commit하지 않습니다. 상태 관리 스크립트에게 다음 prompt를 요청하고 그 prompt를 현재 session에 전달할 뿐입니다.

hook input의 session id가 없거나, run binding이 없거나, hook session id가 run에 바인딩된 session id와 다르면 Stop hook은 no-op 합니다.

어떤 단계가 `running` 상태로 남아 있으면 `--reprompt-running`은 새 작업을 시작하지 않고 같은 단계로 다시 들어가는 prompt를 반환합니다.

## 역할 구분

현재 대화 session이 run을 제어합니다.

- `clarify`, `context-gather`, `plan`은 현재 대화 session이 수행합니다.
- `generate`는 새 구현 subagent 하나에게 phase 파일 하나만 위임합니다.
- `evaluate`는 새 검토 subagent 하나에게 위임합니다.
- subagent는 state command를 호출하지 않습니다.
- subagent는 run 상태를 바꾸지 않습니다.
- subagent는 commit하지 않습니다.
- subagent는 맡은 작업 결과를 보고한 뒤 종료합니다. 현재 대화 session은 가능한 경우 subagent session을 닫습니다.
- 현재 대화 session은 artifact를 쓰고, subagent 결과를 검토하고, 상태를 갱신하고, commit prompt를 처리합니다.

Phaseharness는 설치 시 subagent를 미리 정의하지 않습니다. `generate`와 `evaluate` skill이 해당 단계 실행 시 새 subagent 요청을 만듭니다.

## Run 파일

하나의 run은 아래 파일들을 가집니다.

```text
.phaseharness/runs/<run-id>/
  run.json
  artifacts/
    clarify.md
    context.md
    plan.md
    generate.md
    evaluate.md
  phases/
    phase-001.md
    phase-002.md
```

`run.json`에는 아래 상태가 기록됩니다.

- 현재 stage
- 수동/자동 mode
- loop count
- commit mode
- stage별 상태
- generate phase queue
- evaluate 결과
- commit prompt 처리 결과
- run 시작 시점에 이미 변경되어 있던 파일 목록

## 상태 관리 명령

자동 run 생성:

```bash
python3 .phaseharness/bin/phaseharness-state.py start \
  --mode auto \
  --request "<request>" \
  --loop-count 2 \
  --commit-mode none \
  --json
```

상태 확인:

```bash
python3 .phaseharness/bin/phaseharness-state.py status --json
```

다음 continuation prompt 생성:

```bash
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

active run을 현재 session에 다시 바인딩하고 resume:

```bash
python3 .phaseharness/bin/phaseharness-state.py resume --json
```

병렬 작업용 worktree 생성:

```bash
python3 .phaseharness/bin/phaseharness-worktree.py create --request "<request>" --json
```

stage 상태 기록:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-stage clarify completed --run-id <run-id>
```

generate phase 상태 기록:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-generate-phase phase-001 completed --run-id <run-id>
```

commit prompt 처리 결과 기록:

```bash
python3 .phaseharness/bin/phaseharness-state.py set-commit phase-001 committed --run-id <run-id>
python3 .phaseharness/bin/phaseharness-state.py set-commit final no_changes --run-id <run-id> --message "no eligible changes to commit"
```

## Commit mode

- `none`: commit prompt를 만들지 않습니다.
- `phase`: generate phase가 하나 끝날 때마다 commit을 요청합니다.
- `final`: `evaluate`가 `pass` 또는 `warn`이면 마지막에 한 번 commit을 요청합니다.

Commit prompt에는 아래 정보가 포함됩니다.

- run id
- commit key
- commit mode
- commit 가능한 파일
- run 시작 전부터 변경되어 있어 제외된 파일
- runtime 파일과 도구 연결 파일 중 기본 제외 대상
- 반드시 실행해야 하는 `set-commit` 후속 명령

실제 git commit은 `commit`만 수행해야 합니다. commit message는 phase 완료 여부가 아니라 실제 변경 내용을 설명해야 합니다.

## 안전 규칙

Phaseharness는 workflow 제어와 실제 실행을 분리합니다.

- `phaseharness-state.py`는 run 파일과 prompt만 관리합니다.
- `phaseharness-hook.py`는 Stop hook wrapper입니다.
- Stop hook은 현재 session id에 바인딩된 활성 자동 run이 있을 때만 동작합니다.
- 수동 skill run은 자동으로 이어지지 않습니다.
- 병렬 자동 run은 별도 git worktree에서 실행합니다.
- runtime 파일과 도구 연결 파일은 commit prompt에서 제외됩니다.
- run 시작 시점에 이미 변경되어 있던 파일은 commit prompt에서 제외됩니다.

## Smoke check

설치 후 아래 명령으로 확인합니다.

```bash
python3 .phaseharness/bin/phaseharness-state.py --help
python3 .phaseharness/bin/phaseharness-hook.py --help
python3 .phaseharness/bin/phaseharness-sync-bridges.py --help
python3 .phaseharness/bin/phaseharness-worktree.py --help
python3 -m py_compile .phaseharness/bin/*.py
python3 .phaseharness/bin/phaseharness-state.py next --require-auto --reprompt-running --require-session-binding --json
```

활성 run이 없을 때 기대 출력에는 아래 값이 포함됩니다.

```json
{ "action": "none" }
```
