# phaseloop

Claude Code와 Codex에서 함께 사용할 수 있는 5단계 agent workflow입니다.

phaseloop는 타겟 레포에 provider-neutral harness를 설치합니다. 하나의 명시적인 작업 요청을 artifact, task phase, 구현, 검증으로 나누고, 특정 대화 세션의 기억에 의존하지 않도록 파일에 상태를 남깁니다. 현재 대화 세션은 얇은 실행 진입점으로 두고, 실제 작업은 새 headless 에이전트 세션에서 수행합니다.

## 설치

phaseloop를 설치할 레포에서 Claude Code 또는 Codex를 열고, 에이전트에게 아래 URL을 주세요.

```text
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

이렇게 지시하면 됩니다.

```text
Install phaseloop from this installer document.
```

installer는 `https://github.com/Ssoon-m/phaseloop.git`을 clone한 뒤 canonical core를 복사하고, Claude/Codex bridge를 생성하고, 프로젝트 context docs 초안을 만들고, smoke verification을 실행합니다.

## 작업 시작

설치된 에이전트에게 `phaseloop` skill을 사용하라고 지시하세요.

```text
Use the phaseloop skill to implement <작은 요구사항> with max attempts 3.
```

`phaseloop` skill은 얇은 진입점입니다. `max attempts`를 확인하거나 사용자가 지정한 값을 사용한 뒤, 내부적으로 headless workflow runner를 실행합니다. `max attempts`를 생략하면 에이전트가 한 번 물어보고, 사용자가 기본값을 승인한 뒤에만 시작해야 합니다.

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --provider codex --max-attempts 2 --session-timeout-sec 600
```

Claude Code로 강제 실행하려면 `--provider claude`를 사용하세요. `--provider`를 생략하면 설정된 기본 provider를 사용합니다.

## 동작 방식

phaseloop는 하나의 요청을 5단계로 실행합니다.

```text
clarify -> context gather -> plan -> generate -> evaluate
```

- `clarify`: 사용자의 요구사항, 완료 조건, 가정, 제외 범위를 이해합니다.
- `context gather`: 참고해야 할 문서, 코드, 패턴, 제약사항을 찾습니다.
- `plan`: task 상태와 구현 phase 파일을 만듭니다.
- `generate`: 계획된 phase를 실행해 구현합니다.
- `evaluate`: 완료 조건과 acceptance criteria를 기준으로 결과를 검증합니다.

각 단계는 `tasks/<task-dir>/artifacts/` 아래에 artifact를 남깁니다. 다음 단계는 대화 기억이 아니라 이전 단계의 artifact 파일을 읽고 진행합니다.

기본 에이전트 세션 전략은 balanced입니다.

```text
analysis session: clarify + context gather + plan
build session(s): planned implementation phases
evaluate session: independent verification
```

즉 전체 작업을 한 대화에 전부 쌓지 않으면서도, 작은 논리 단계마다 매번 새 에이전트 세션을 띄우지는 않아서 기본 컨텍스트를 반복 로드하는 낭비를 줄입니다.

`--max-attempts`는 analysis session, 각 build phase, evaluate session이 실패했을 때 몇 번까지 재시도할지를 정합니다. 무한 루프 횟수가 아니라 재시도 예산입니다. 최대 횟수를 넘으면 `tasks/<task-dir>/index.json`에 실패 상태가 기록됩니다.

`--session-timeout-sec`는 headless 에이전트 세션 또는 build phase 호출 하나가 몇 초까지 실행될 수 있는지를 정합니다. 시간이 넘으면 실패로 기록하고 재시도합니다.

## 생성되는 상태

작업을 실행하면 대략 아래와 같은 파일이 생성됩니다.

```text
tasks/<task-dir>/
  index.json
  artifacts/
    01-clarify.md
    02-context.md
    03-plan.md
    04-generate.md
    05-evaluate.md
  phase0.md
  phase1.md
  analysis-output-attempt1.json
  phase0-output.json
  generate-output.json
  evaluate-output-attempt1.json
```

canonical harness는 `.agent-harness/` 아래에 있습니다. 런타임별 파일은 generated bridge입니다.

```text
.agent-harness/
  skills/phaseloop/
  roles/phase-*/

.claude/skills
.claude/agents/phase-*.md
.claude/hooks/phaseloop-sync-bridges.sh
.agents/skills
.codex/agents/phase-*.toml
.codex/hooks/phaseloop-sync-bridges.sh
```

수정이 필요하면 `.agent-harness/` 아래 canonical 파일을 수정하세요. `.claude/`, `.agents/`, `.codex/` 아래 generated bridge 파일을 직접 수정하지 않는 것이 원칙입니다.

bridge sync hook은 `.agent-harness/`가 바뀌었을 때 runtime bridge를 다시 생성합니다. 기존 Claude/Codex hooks는 보존하고, phaseloop가 추가한 hook entry만 추가하거나 갱신합니다.

## 모노레포

phaseloop는 workflow 상태를 소유할 디렉토리에서 설치하세요.

- 레포 전체 workflow: 모노레포 루트에서 설치
- 앱 단위 workflow: `apps/<app>` 또는 대상 package 디렉토리에서 설치

루트 설치와 앱 단위 설치는 함께 존재할 수 있지만, 각각 별도의 scope이며 별도의 `tasks/` 상태를 가집니다.

## 저장소 구조

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

## 로컬 개발

local smoke test:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/scripts/*.py core/.agent-harness/providers/*.py tests/smoke_install.py
```

로컬 checkout에서 설치 테스트를 하려면:

```bash
export HARNESS_SOURCE=/absolute/path/to/phaseloop
```

그 다음 임시 타겟 레포에서 에이전트에게 `installer/install-harness.md`를 주세요.
