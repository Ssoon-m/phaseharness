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

`phaseloop` skill은 얇은 진입점입니다. `max attempts`와 `commit mode`를 확인하거나 사용자가 지정한 값을 사용한 뒤, 내부적으로 headless workflow runner를 실행합니다. 둘 중 하나를 생략하면 에이전트가 한 번 물어보고, 사용자가 기본값을 승인한 뒤에만 시작해야 합니다.

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --provider codex --max-attempts 2 --session-timeout-sec 600 --commit-mode none
```

Claude Code로 강제 실행하려면 `--provider claude`를 사용하세요. `--provider`를 생략하면 설정된 기본 provider를 사용합니다.

`commit mode`의 기본값은 `none`입니다. 사용자가 미리 지정하지 않았다면 skill 시작 시 어떤 모드로 실행할지 물어봐야 합니다.

- `none`: 자동 커밋하지 않음
- `final`: 전체 workflow가 성공한 뒤 커밋 1개 생성
- `phase`: generate phase가 완료될 때마다 커밋 생성

예시:

```text
Use the phaseloop skill to implement <작은 요구사항> with max attempts 3 and commit mode final.
Use the phaseloop skill to implement <큰 요구사항> with max attempts 3 and commit mode phase.
```

내부적으로는 아래 옵션을 붙이는 흐름입니다.

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --provider codex --max-attempts 3 --session-timeout-sec 600 --commit-mode final
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <larger request>" --provider codex --max-attempts 3 --session-timeout-sec 600 --commit-mode phase
```

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

## 결과 커밋

phaseloop에는 완료된 workflow 결과와 현재 세션 변경을 안전하게 커밋하기 위한 `commit` skill이 포함됩니다.

자동 workflow 커밋은 `--commit-mode`로 제어합니다.

- `none`은 기본값이며 변경 사항을 자동 커밋하지 않습니다.
- `final`은 evaluation이 `pass` 또는 `warn`일 때 완료된 task 결과를 커밋합니다.
- `phase`는 workflow 진행 중 완료된 generate phase를 커밋합니다. evaluation은 로컬 task state로만 남기며 빈 validation 커밋은 만들지 않습니다.

기본 product commit에는 `tasks/<task-dir>/artifacts/*`가 들어가지 않습니다. 대신 commit subject는 작업 요청이나 phase metadata에서 가져온 작업 중심 문구를 사용합니다. 즉 git history에는 어떤 작업을 했는지가 남고, phaseloop 내부 경로와 전체 artifact는 로컬 `tasks/` 상태로 유지됩니다. 설치된 타겟 레포에는 `tasks/.gitignore`도 같이 들어가므로 runtime task 디렉토리는 명시적으로 커밋하지 않는 한 로컬 상태로 남습니다.

최신 완료 task를 커밋하려면 이렇게 말하면 됩니다.

```text
Use the commit skill to commit the latest phaseloop result.
```

스크립트를 직접 실행할 수도 있습니다.

```bash
python3 scripts/commit-result.py
```

특정 task만 지정하려면:

```bash
python3 scripts/commit-result.py <task-dir>
```

phaseloop task artifact까지 의도적으로 커밋하고 싶을 때만:

```bash
python3 scripts/commit-result.py <task-dir> --include-harness-state
```

`commit-result.py`는 task가 완료됐는지, evaluation이 `pass` 또는 `warn`인지, workflow 도중 `git HEAD`가 바뀌지 않았는지, workflow 시작 전에 이미 dirty였던 파일이 섞이지 않는지를 확인합니다. dirty worktree에서 workflow를 시작했다면 자동 커밋은 보통 멈추고 수동 판단을 요구합니다. 가장 안전한 방식은 clean worktree에서 commit mode workflow를 시작하고, 실행 중 같은 레포를 따로 수정하지 않는 것입니다.

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

설치된 타겟 레포에서 `tasks/` 아래 runtime task 상태는 기본적으로 gitignore됩니다. 이 파일들은 agent workflow를 위한 로컬 durable state이며, product history가 아닙니다.

canonical harness는 `.agent-harness/` 아래에 있습니다. 런타임별 파일은 generated bridge입니다.

```text
.agent-harness/
  skills/phaseloop/
  skills/commit/
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
