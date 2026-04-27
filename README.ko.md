# phaseloop

Claude Code와 Codex에서 사용할 수 있는 portable five-phase agent workflow입니다.

phaseloop는 provider-neutral harness를 대상 저장소에 설치합니다. 하나의
명시적인 작업 요청을 durable task state, implementation phase, evaluation으로
나누어 한 대화의 긴 컨텍스트에 의존하지 않고 작업을 진행합니다.

## 설치

대상 저장소에서 Claude Code 또는 Codex를 열고, 아래 문장을 그대로 요청합니다.

```text
Install phaseloop from this installer document:
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

installer는 canonical harness를 복사하고, Claude/Codex bridge를 생성하고,
starter project docs와 local task state를 만든 뒤 smoke verification을
실행합니다.

workflow state를 소유할 디렉터리에서 설치하세요. 모노레포라면 레포 루트나
특정 app/package 디렉터리 중 하나를 선택할 수 있습니다.

## 작업 실행

설치된 skill을 사용합니다.

```text
Use the phaseloop skill to implement <request> with max attempts 3 and commit mode none.
```

`max attempts`는 각 workflow session 또는 build phase의 retry budget입니다.
`commit mode`는 phaseloop가 git commit을 자동으로 만들지 여부를 제어합니다.
둘 중 하나를 생략하면 skill이 기본값을 사용하기 전에 한 번 확인합니다.

직접 실행할 수도 있습니다.

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <request>" \
  --max-attempts 3 \
  --session-timeout-sec 600 \
  --commit-mode none
```

`--provider claude` 또는 `--provider codex`를 지정하면 설정된 headless runtime을
override합니다. 이 runtime은 phaseloop를 시작한 현재 에이전트 세션과 다를 수
있습니다.

## Commit Mode

기본값은 `none`입니다.

- `none`: 변경사항을 자동 커밋하지 않습니다.
- `final`: evaluation이 `pass` 또는 `warn`이면 product commit 하나를 만듭니다.
- `phase`: 완료된 generate phase마다 commit을 만듭니다. Evaluation은 로컬 상태로
  남기며 빈 validation commit을 만들지 않습니다.

Product commit은 기본적으로 phaseloop task artifact를 포함하지 않습니다. 설치된
저장소에서는 `tasks/` 아래 runtime task state가 기본적으로 로컬 상태로
유지됩니다.

commit script는 task 완료 여부, evaluation 상태, HEAD 이동 여부, workflow 시작 전
dirty path를 확인한 뒤 commit을 만듭니다.

최신 완료 task result를 수동으로 커밋하려면:

```bash
python3 scripts/commit-result.py
```

특정 task를 커밋하려면:

```bash
python3 scripts/commit-result.py <task-dir>
```

phaseloop state를 의도적으로 포함하려면:

```bash
python3 scripts/commit-result.py <task-dir> --include-harness-state
```

## 동작 방식

phaseloop는 하나의 요청을 다섯 logical phase로 실행합니다.

```text
clarify -> context gather -> plan -> generate -> evaluate
```

기본 실행 방식은 앞의 세 분석 단계를 한 세션에서 처리하고, 구현과 검증은 별도
세션으로 나눕니다.

```text
analysis: clarify + context gather + plan
build: planned implementation phases
evaluate: independent verification
```

이 구조는 현재 대화를 작게 유지하고, 작은 logical phase마다 provider session을
다시 시작하는 비용을 줄이며, 최종 evaluation을 implementation session과
분리합니다. 이것이 기본 `balanced` strategy입니다.

## State 위치

Task state는 `tasks/` 아래에 저장되며, 설치된 저장소에서는 기본적으로
gitignored됩니다.

Canonical harness 파일은 `.agent-harness/` 아래에 있습니다. Claude와 Codex
runtime bridge는 이 canonical source에서 생성됩니다.

Harness를 수정할 때는 `.agent-harness/`를 수정하세요. `.claude/`, `.agents/`,
`.codex/` 아래 generated bridge file은 runtime output으로 취급합니다.

## 개발

로컬 검증:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/scripts/*.py core/.agent-harness/providers/*.py tests/smoke_install.py
```

구현 세부사항은 `SPEC.md`와 `spec/`를 참고하세요.
