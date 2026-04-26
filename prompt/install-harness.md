# install-harness

> **쓰는 법.** 이 파일 전체를 복사해서, 하네스를 설치하려는 **타겟 프로젝트의 에이전트 세션**에 그대로 붙여넣는다. 목적은 특정 벤더 전용 자산을 복제하는 것이 아니라, **Claude / Codex 중 어떤 런타임으로도 구동 가능한 provider-neutral 자율 하네스**를 타겟 프로젝트에 맞게 스캐폴드하는 것이다.

---

너(에이전트)는 지금 **타겟 프로젝트 레포 루트**에서 실행 중이다. 아래 절차를 **순서대로** 수행해 이 프로젝트에 "요구사항 발굴 → 계획 수립 → phase 실행 → 검증 → 실패 시 롤백" 루프를 설치하라.

핵심 원칙:

- 이 작업은 **다른 저장소의 파일을 무조건 복사하는 작업이 아니다**. 타겟 프로젝트의 구조, 스택, 테스트 방식, 현재 실행 가능한 CLI를 먼저 읽고, 그에 맞는 하네스를 **직접 생성/조정**한다.
- Claude/Codex 어느 쪽에서 실행되더라도 동작해야 한다. 따라서 `.claude/skills` 같은 특정 런타임 전용 구조를 핵심 계약으로 삼지 말고, **파일 산출물 계약**과 **provider adapter**를 핵심으로 설계하라.
- 이미 존재하는 파일/디렉토리를 무조건 덮어쓰지 마라. 충돌 시 diff를 읽고, 안전하게 merge하거나 필요한 경우에만 사용자에게 확인받아라.
- 가능한 한 **타겟 프로젝트의 기존 dev/test 커맨드, 기존 docs, 기존 git 관례**를 재사용하라. 새 커맨드나 구조를 불필요하게 invent 하지 마라.

---

## 0. 사전 확인

먼저 아래를 확인하라.

```bash
pwd
git rev-parse --verify HEAD
git status --short
ls
command -v python3
command -v claude || true
command -v codex || true
```

그리고 아래도 빠르게 파악하라.

```bash
ls README.md docs package.json pyproject.toml go.mod Cargo.toml Gemfile pubspec.yaml 2>/dev/null
```

중단 조건:

- git 초기 커밋이 없으면 중단. rollback 기준점이 없다.
- `python3`가 없으면 중단.
- `claude`와 `codex`가 둘 다 없으면 중단.

작업 트리가 dirty여도 곧장 중단하지는 말고, **무관한 변경이 섞일 위험이 있다**는 점만 짧게 보고한 뒤 진행한다. 단, harness가 덮어쓸 가능성이 있는 파일(`scripts/run-server.py`, `scripts/run-phases.py`, `.agent-harness/`, `docs/mission.md` 등)이 이미 수정 중이면 먼저 충돌 여부를 정밀 확인하라.

---

## 1. 설치 전략 결정

이 프로젝트에 설치할 하네스의 기본 구조는 아래와 같다.

```text
<repo_root>/
  .agent-harness/
    config.json
    prompts/
      ideation.md
      build.md
      check.md
      rollback.md
      task-create.md
    providers/
      base.py
      claude.py
      codex.py
      registry.py
  scripts/
    run-server.py
    run-phases.py
    gen-docs-diff.py
    _utils.py
  docs/
    mission.md
    spec.md
    testing.md
    user-intervention.md
  iterations/
  tasks/
```

설계 원칙:

- `scripts/`는 orchestration만 담당한다.
- `.agent-harness/providers/`는 Claude/Codex CLI 차이를 캡슐화한다.
- `.agent-harness/prompts/`는 provider-neutral prompt pack이다.
- `tasks/`, `iterations/`, `index.json`, `check-report.json` 같은 **상태 파일 포맷**이 표준 계약이다.

### 1.1 Provider 결정 규칙

다음 규칙으로 provider 전략을 정하라.

- `claude`만 있으면 기본 provider는 `claude`
- `codex`만 있으면 기본 provider는 `codex`
- 둘 다 있으면:
  - 둘 다 adapter를 만든다.
  - 기본값은 **현재 세션을 돌리고 있는 런타임과 가장 가까운 것**으로 잡되,
  - `config.json`에서 언제든 바꿀 수 있게 한다.

중요:

- Codex CLI의 비대화형 실행 플래그를 **추측하지 말고**, 반드시 `codex --help` 또는 관련 help 명령을 먼저 읽어 실제 설치된 버전에 맞게 adapter를 작성하라.
- Claude CLI도 동일하다. 가능하면 `claude --help`를 읽어 실제 사용 가능한 non-interactive invocation을 확인하라.
- 단, provider interface는 동일해야 한다.

---

## 2. 프로젝트 컨텍스트 파일 준비

하네스는 아래 문서를 읽고 요구사항 발굴/구현 계획을 세운다.

- `docs/mission.md`
- `docs/spec.md`
- `docs/testing.md`
- `docs/user-intervention.md`

이미 유사 문서가 있으면 재사용하고, 없으면 초안을 작성하라.

작성 규칙:

- `mission.md`: 제품 목표, 핵심 사용자, 현재 단계, 하지 않을 것
- `spec.md`: 현재 화면/명령/API/데이터 흐름. 이미 존재하는 구조를 기준으로 쓴다.
- `testing.md`: build/test/lint/dev 실행 규칙, mock 허용 여부, 반드시 통과해야 할 AC 커맨드
- `user-intervention.md`: AI 에이전트가 직접 할 수 없는 배포/승인/외부 시스템 조작 항목

문서가 전혀 없을 때도 빈 파일을 만들지 말고, 레포를 읽어 최소 초안을 작성하라.

---

## 3. 하네스 디렉토리와 상태 디렉토리 생성

다음 디렉토리를 생성하라.

```bash
mkdir -p .agent-harness/prompts .agent-harness/providers scripts docs iterations tasks
```

그리고 `tasks/index.json`이 없으면 최소 스키마로 생성하라.

```json
{
  "tasks": []
}
```

`iterations/`는 비워둬도 된다.

---

## 4. Provider-neutral prompt pack 작성

다음 파일들을 작성하라.

### 4.1 `.agent-harness/prompts/task-create.md`

역할:

- 구현 계획을 `tasks/{id}-{slug}/` 아래 phase 파일로 쪼개는 규격 문서

필수 계약:

- phase 0는 문서 업데이트
- 각 phase는 독립 세션에서 실행 가능해야 함
- AC는 반드시 **실행 가능한 커맨드**
- 성공/실패 시 `tasks/{task-dir}/index.json`의 phase status를 갱신
- `docs-diff.md`는 phase 0 이후 `gen-docs-diff.py`가 생성

### 4.2 `.agent-harness/prompts/ideation.md`

역할:

- 현재 구현 상태와 문서를 읽고, 다음 iteration에 구현할 **단 하나의 요구사항**을 뽑는다.

필수 계약:

- 사용자 질문 없이 진행 가능해야 한다.
- 결과는 `iterations/<iter-id>/requirement.md`에 저장한다.
- 출력 구조는 최소 아래 내용을 포함한다.

```markdown
# Requirement

## Context
- 왜 지금 이 요구사항을 우선하는가

## Requirement
- title:
- user pain:
- expected change:

## Constraints
- 기술/운영 제약

## Validation Hint
- 구현 후 무엇을 확인해야 하는가
```

### 4.3 `.agent-harness/prompts/build.md`

역할:

- `requirement.md`를 읽고 문서를 업데이트하고, task/phase를 만들고, `scripts/run-phases.py`를 실행하는 빌드 세션용 prompt

필수 계약:

- 문서 파악 → 구현 계획 → task 생성 → phase 실행
- 질문 대신 합리적 기본값 선택
- provider/tool 이름을 prompt 안에 박지 말고, 필요한 산출물만 지시

### 4.4 `.agent-harness/prompts/check.md`

역할:

- 가장 최근 task의 상태를 읽고, 이번 iteration이 직전 iteration 대비 개선/퇴행/불명확인지 판정

반드시 `iterations/<iter-id>/check-report.json`에 아래 스키마를 쓰게 하라.

```json
{
  "iter_id": "<iter-id>",
  "status": "pass|warn|fail",
  "task": {
    "dir": "tasks/<task-dir>|null",
    "name": "<task-name>|null",
    "overall_status": "completed|error|incomplete|not_created"
  },
  "phases": [],
  "issues": [],
  "conclusion": "",
  "carry_over": [],
  "progress": {
    "previous_iter_id": null,
    "signal": "improved|regressed|inconclusive|no_prior_run",
    "summary": ""
  }
}
```

### 4.5 `.agent-harness/prompts/rollback.md`

역할:

- build 실패 시 build 직전 HEAD로 원복하는 prompt

필수 계약:

- 기준 commit SHA는 prompt에서 주입
- `git reset --hard <sha>` 후 검증
- 필요하면 빈 marker commit 남김
- push 금지

---

## 5. Provider adapter 작성

다음 파일들을 작성하라.

### 5.1 `.agent-harness/providers/base.py`

공통 인터페이스:

```python
class ProviderResult(TypedDict):
    exit_code: int
    stdout: str
    stderr: str


class Provider(Protocol):
    def run(
        self,
        prompt: str,
        *,
        cwd: str,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
        capture_json: bool = False,
    ) -> ProviderResult: ...
```

### 5.2 `.agent-harness/providers/claude.py`

규칙:

- 현재 설치된 Claude CLI help를 읽고 **실제 지원되는 비대화형 플래그**를 기준으로 구현
- 가능하면 absolute path 또는 `shutil.which()`로 바이너리 결정
- headless일 때 `AGENT_HEADLESS=1`을 env에 주입
- 필요한 경우 permission bypass 플래그 사용

### 5.3 `.agent-harness/providers/codex.py`

규칙:

- 현재 설치된 Codex CLI help를 읽고 **실제 지원되는 비대화형 플래그**를 기준으로 구현
- headless 환경변수 주입
- stdout/stderr 수집
- prompt를 인자로 넘기거나 stdin으로 넘기는 방식은 **현재 설치된 CLI가 지원하는 쪽**을 따른다

### 5.4 `.agent-harness/providers/registry.py`

역할:

- `config.json`과 실제 설치된 CLI를 보고 provider 선택
- `default_provider`, `fallback_provider` 지원

---

## 6. 공통 스크립트 작성

다음 스크립트를 작성하라.

### 6.1 `scripts/_utils.py`

포함할 것:

- `find_project_root()`
- `load_json()`, `save_json()`
- `now_iso()`
- provider 로딩 helper

### 6.2 `scripts/gen-docs-diff.py`

역할:

- baseline commit과 현재 `docs/` diff를 `tasks/<task-dir>/docs-diff.md`로 저장

### 6.3 `scripts/run-phases.py`

역할:

- `tasks/<task-dir>/index.json`을 읽고 다음 pending phase 실행
- `.agent-harness/prompts/`의 공통 규약을 적용
- phase prompt는 **파일 경로만 넘기지 말고 파일 내용을 prompt에 포함**한다
- provider adapter를 통해 비대화형 실행
- 결과를 `phaseN-output.json`에 저장
- phase status가 `completed|error|pending` 중 무엇으로 끝났는지 검사
- phase 0 완료 시 `gen-docs-diff.py` 호출

추가 권장사항:

- 시작 전 dirty worktree 경고
- fallback commit과 housekeeping commit을 분리
- 무관 파일이 섞이지 않도록 가능한 한 경로 기반 staging

### 6.4 `scripts/run-server.py`

역할:

- 무한 iteration 루프
- 순서:
  1. ideation
  2. commit ideation artifacts
  3. build
  4. check
  5. 필요 시 rollback
  6. sleep

필수 규칙:

- 모든 서브세션에 `AGENT_HEADLESS=1` 주입
- `stdin=DEVNULL`로 실행
- 단계별 timeout 적용
- iteration marker(예: `iter-id: ...`)를 커밋 메시지 trailer로 강제

---

## 7. Headless 규약

이 하네스의 canonical headless 신호는:

```bash
AGENT_HEADLESS=1
```

prompt pack과 provider는 이 규약을 따른다.

의미:

- 질문 금지
- confirm 대기 금지
- 애매하면 합리적 기본값 선택
- 결정 근거는 파일에 기록
- 실패 시 상태 파일에 남기고 종료

중요:

- Claude/Codex 어느 provider를 쓰더라도 이 규약은 동일해야 한다.
- 특정 벤더명(`HARNESS_HEADLESS`, `BET_HEADLESS`)을 핵심 표준으로 삼지 마라.

---

## 8. README 반영

타겟 프로젝트 README에 짧은 섹션을 추가하라.

포함할 내용:

- 이 프로젝트가 왜 하네스를 쓰는지
- 어디에 상태가 쌓이는지 (`tasks/`, `iterations/`)
- 기본 실행 커맨드
- headless 신호 이름 (`AGENT_HEADLESS`)

---

## 9. 검증

설치 후 아래를 검증하라.

```bash
python3 scripts/run-server.py --help || true
python3 scripts/run-phases.py --help || true
python3 scripts/gen-docs-diff.py --help || true
python3 -m py_compile scripts/*.py .agent-harness/providers/*.py
```

그리고 provider가 최소한 감지 가능한지도 확인하라.

```bash
command -v claude || true
command -v codex || true
```

CLI 형식이 불명확하면 `--help`를 읽고 adapter를 보정하라. **추측으로 마무리하지 마라.**

---

## 10. 보고 형식

작업을 마치면 아래를 보고하라.

- 생성/수정한 파일 목록
- 기본 provider / fallback provider
- 아직 사람이 채워야 하는 문서나 값
- 첫 실행 커맨드
- 남은 리스크

커밋 제안 메시지:

```text
chore(harness): install provider-neutral autonomous harness

- add provider adapters for Claude/Codex
- scaffold prompt pack and orchestration scripts
- add docs/task/iteration state structure
- document AGENT_HEADLESS workflow
```

---

## 자주 하는 실수 (하지 말 것)

- ❌ Claude 전용 skill 구조를 그대로 박아 넣고 Codex 경로를 나중에 생각하기
- ❌ Codex CLI 플래그를 추측으로 구현하기
- ❌ 상태 계약 없이 prompt만 길게 쓰기
- ❌ `tasks/`와 `iterations/`를 로그 디렉토리처럼만 취급하기
- ❌ phase prompt에 파일 경로만 주고 실제 내용을 안 넣기
- ❌ dirty worktree를 무시하고 `git add -A`로 전부 커밋하기
- ❌ rollback 기준 HEAD 없이 무한 루프부터 돌리기
- ❌ `AGENT_HEADLESS=1` 규약을 prompt pack과 provider 양쪽에 동시에 반영하지 않기
