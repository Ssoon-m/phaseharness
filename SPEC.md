# SPEC

## 1. Purpose

이 프로젝트의 목적은 특정 런타임 전용 자동화 세트를 만드는 것이 아니라, **Claude Code와 Codex가 함께 사용할 수 있는 설치형 하네스 표준**을 정의하고 제공하는 것이다.

핵심 사용 시나리오:

1. 사용자가 자기 레포에서 에이전트 세션을 연다.
2. 이 프로젝트가 제공하는 `install-harness.md`를 타겟 레포 세션에 던진다.
3. 에이전트가 이 프로젝트의 **canonical core**를 기준으로 타겟 레포에 하네스를 설치한다.
4. 이후 그 타겟 레포 안에서 Claude Code든 Codex든 같은 상태 계약으로 하네스를 실행한다.

즉 이 프로젝트는 다음 두 가지를 함께 제공해야 한다.

- **canonical harness core**
- **installer documents**

---

## 2. Non-goals

이 프로젝트의 비목표는 아래와 같다.

- 타겟 레포마다 제각각 다른 하네스를 즉석 생성하는 것
- `.claude/skills` 같은 Claude 전용 구조를 표준으로 삼는 것
- Claude/Codex의 native subagent 파일 포맷을 하나로 억지 통합하는 것
- Codex/Claude prompt 문장을 완전히 동일하게 만드는 것
- context가 부족해도 무조건 자동 진행시키는 것
- 처음부터 무한 루프를 기본 동작으로 두는 것

---

## 3. Canonical Model

이 프로젝트는 "에이전트가 대화를 기억해서 이어간다"는 가정보다, **파일과 git을 기준으로 상태를 이어가는 시스템**을 지향한다.

표준의 중심은 아래 네 가지다.

- 상태 파일 계약
- phase lifecycle 계약
- runtime provider 계약
- skill/role bridge 계약

런타임은 Claude/Codex로 바뀔 수 있지만, 위 계약들은 바뀌지 않아야 한다.

---

## 4. Canonical Repository Layout

이 저장소 안의 canonical 구조는 아래를 목표로 한다.

```text
<repo_root>/
  SPEC.md
  spec/
    PURPOSE.md
    CONTRACT.md
    PROVIDERS.md
    BRIDGES.md
  installer/
    install-harness.md
  core/
    .agent-harness/
      config.toml
      skills/
      roles/
      prompts/
      providers/
    scripts/
      _utils.py
      gen-bridges.py
      gen-docs-diff.py
      run-phases.py
      run-server.py
    templates/
      docs/
```

중요 원칙:

- `installer/`는 **설치 절차 문서**
- `core/`는 **실제 설치될 canonical implementation**
- `spec/`은 설계 기준 문서

현재 상태:

- `spec/` 문서가 존재한다.
- `core/` 아래 canonical implementation 초안이 존재한다.
- canonical installer는 `installer/install-harness.md`다.

---

## 5. Target Repository Layout

타겟 레포에 설치된 뒤의 구조는 아래를 목표로 한다.

```text
<target_repo>/
  .agent-harness/
    config.toml
    skills/
      ideation/
      plan-and-build/
    roles/
      tech-critic-lead/
        role.toml
        prompt.md
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
    _utils.py
    gen-bridges.py
    gen-docs-diff.py
    run-phases.py
    run-server.py
  docs/
    mission.md
    spec.md
    testing.md
    user-intervention.md
  tasks/
  iterations/

  # runtime-specific generated bridges, optional
  .claude/
    skills/ -> ../.agent-harness/skills
    agents/
      tech-critic-lead.md
  .agents/
    skills/ -> ../.agent-harness/skills
  .codex/
    agents/
      tech-critic-lead.toml
```

`.claude/` 경로는 canonical이 아니다. 필요하면 Claude 호환용 bridge로만 취급한다.
`.agents/`와 `.codex/`도 canonical이 아니라 Codex 호환용 bridge로만 취급한다.

---

## 5.1 Skill and Role Bridge Contract

### 5.1.1 Skills

skill의 canonical source는 `.agent-harness/skills/`다.

Claude Code와 Codex가 모두 같은 skill 본문을 읽을 수 있도록, 런타임별 skill 경로는 bridge로만 만든다.

- Claude bridge: `.claude/skills`
- Codex/agent bridge: `.agents/skills`

bridge는 가능하면 symlink로 만들고, symlink가 안전하지 않은 환경에서는 installer가 generated copy를 만든다.
어느 경우든 canonical 수정 대상은 `.agent-harness/skills/`뿐이다.

### 5.1.2 Roles

subagent는 런타임별 인터페이스가 다르므로 직접 공유하지 않는다.

role의 canonical source는 `.agent-harness/roles/<role-name>/`다.

```text
.agent-harness/roles/<role-name>/
  role.toml
  prompt.md
```

`role.toml`은 최소 아래 개념을 담는다.

- `name`
- `description`
- `model_tier`
- `sandbox_mode`
- `tools_policy`
- `output_schema`

`prompt.md`는 해당 role의 실제 시스템 지침이다.

installer 또는 `scripts/gen-bridges.py`는 canonical role을 기준으로 아래 runtime bridge를 생성한다.

- Claude bridge: `.claude/agents/<role-name>.md`
- Codex bridge: `.codex/agents/<role-name>.toml`

중요:

- `.claude/agents/*.md`와 `.codex/agents/*.toml`은 생성물이다.
- 이 생성물을 canonical source로 편집하지 않는다.
- native subagent 기능은 UX 최적화일 뿐, phase lifecycle의 필수 계약이 아니다.
- 자동 실행의 표준은 provider의 `run_role()` 계약으로 보장한다.

---

## 6. Shared State Contract

### 6.1 Core state files

표준 상태 파일은 최소 아래를 포함한다.

- `tasks/index.json`
- `tasks/<task-dir>/index.json`
- `tasks/<task-dir>/phase<N>.md`
- `tasks/<task-dir>/phase<N>-output.json`
- `tasks/<task-dir>/docs-diff.md`
- `tasks/<task-dir>/role-<role-name>-output.json`
- `iterations/<iter-id>/requirement.md`
- `iterations/<iter-id>/check-report.json`
- `iterations/<iter-id>/role-<role-name>-output.json`

### 6.2 Contract principle

런타임 교체 가능성은 **prompt wording**이 아니라 **이 파일들의 구조와 의미**를 통해 보장한다.

### 6.3 Schema version

상태 파일 스키마에는 추후 `schema_version` 필드 도입을 고려한다. 설치형 표준은 업그레이드 경로가 필요하기 때문이다.

---

## 7. Phase Lifecycle

공통 phase lifecycle은 아래와 같다.

1. 요구사항 발굴
2. 문서 기반 계획 수립
3. task 생성
4. phase별 실행
5. 검증
6. 실패 시 rollback

세부 계약:

- phase 0는 문서 업데이트
- 각 phase는 독립 세션에서 실행 가능해야 함
- AC는 반드시 실행 가능한 커맨드
- 성공/실패는 `tasks/<task-dir>/index.json`에 기록
- phase 결과 원문은 `phase<N>-output.json`에 저장
- phase 0 이후 `docs-diff.md` 생성

---

## 8. Headless Semantics

canonical headless 신호는 아래로 통일한다.

```bash
AGENT_HEADLESS=1
```

의미는 다음과 같다.

- 질문 금지
- confirm 대기 금지
- 가능한 범위에서 합리적 기본값 선택
- 단, context가 부족하면 강행하지 말고 상태 파일에 남기고 종료
- 승인 요청 UI에 의존하지 않음

중요:

- `AGENT_HEADLESS=1`은 "무조건 진행"이 아니라 **사용자 왕복 없이 결정 가능한 범위에서만 자동 진행**을 뜻한다.
- 맥락이 불충분하면 `context_insufficient`로 실패해야 한다.

기존 `HARNESS_HEADLESS`, `BET_HEADLESS`는 canonical 명칭이 아니다.

---

## 9. Failure Categories

무인 실행에서 단순 `error` 하나로 끝내면 안 된다. 최소 아래 구분이 필요하다.

- `validation_failed`
- `sandbox_blocked`
- `context_insufficient`
- `runtime_error`

이유:

- Codex는 `approval=never`로 돌릴 때 sandbox에 막힐 수 있다.
- 이 경우 사용자 승인 요청 대신 상태 파일에 명시적 실패 사유를 남겨야 다음 iteration 또는 intervention 판단이 가능하다.

---

## 10. Provider Abstraction

### 10.1 Canonical provider interface

provider는 최소 아래 개념을 받아야 한다.

- `prompt`
- `cwd`
- `env`
- `timeout_sec`
- `sandbox_mode`
- `approval_policy`
- `prompt_handoff`
- `capture_json`

또한 provider는 native subagent 기능과 별개로 아래 role 실행 개념을 지원해야 한다.

- `role_name`
- `role_prompt`
- `role_input`
- `output_schema`
- `output_path`

즉 provider에는 최소 두 실행 모드가 있다.

- `run_prompt()`: 일반 prompt 세션 실행
- `run_role()`: canonical role을 독립 세션으로 실행하고 구조화된 결과 저장

### 10.2 Runtime-neutral principle

오케스트레이터는 provider-neutral이어야 한다.

- `run-server.py`는 순서와 상태만 관리
- `run-phases.py`는 phase lifecycle만 관리
- `run_role()` 결과는 JSON 상태 파일로만 판단
- Claude/Codex invocation 차이는 `providers/`와 generated bridge에만 존재

예를 들어 `tech-critic-lead`의 판단 결과는 최소 아래처럼 구조화되어야 한다.

```json
{
  "role": "tech-critic-lead",
  "decision": "approve|revise|reject",
  "reasons": [],
  "required_changes": [],
  "human_intervention_required": false
}
```

---

## 11. Claude Policy

Claude 쪽 canonical 무인 실행 모델은 현재 기준으로 아래 패턴을 따른다.

```bash
claude -p --dangerously-skip-permissions
```

참고:

- `-p`는 non-interactive 실행
- `--dangerously-skip-permissions`는 권한 확인 생략

단, 이 플래그 조합 자체가 표준은 아니다. **표준은 의미**이고, Claude adapter가 그 의미를 현재 CLI에 맞게 구현하는 것이다.

Claude bridge 정책:

- `.claude/skills`는 `.agent-harness/skills`의 symlink 또는 generated copy다.
- `.claude/agents/*.md`는 `.agent-harness/roles/*`에서 생성한다.
- Claude native subagent 자동 위임에 의존하지 않는다.
- provider가 native subagent를 사용할 수 있더라도 canonical 결과는 `run_role()`의 JSON output으로 검증한다.

---

## 12. Codex Policy

Codex도 완전 무인 실행을 1급 시나리오로 지원해야 한다.

canonical 기본 방침:

- `codex exec`
- `--sandbox workspace-write`
- `--ask-for-approval never`
- 가능하면 `--ignore-user-config`
- 가능하면 `--ephemeral`
- prompt handoff는 기본적으로 `stdin`

중요:

- `on-request`는 무인 표준이 아니다. 승인 UI에 기대기 때문이다.
- `read-only`는 build/run-phases/rollback 기본값이 될 수 없다.
- sandbox에 막히면 승인 요청이 아니라 `sandbox_blocked`를 기록해야 한다.

Codex bridge 정책:

- `.agents/skills`는 `.agent-harness/skills`의 symlink 또는 generated copy다.
- `.codex/agents/*.toml`은 `.agent-harness/roles/*`에서 생성한다.
- Codex는 subagent를 명시적으로 요청했을 때만 spawn한다는 전제에 맞춘다.
- headless harness는 암묵적 자동 위임에 기대지 않고, provider가 explicit role invocation을 수행한다.

---

## 13. Installer Role

installer 문서는 아래 역할만 수행해야 한다.

- preflight
- provider 감지
- canonical core 복사 또는 병합
- skill/role bridge 생성
- 프로젝트 문맥 문서 생성/보강
- config 작성
- smoke verification

installer가 하면 안 되는 것:

- 타겟 레포 안에서 하네스 전체를 즉석 설계하기
- canonical core 없이 새 구현을 마구 생성하기
- 프로젝트 문맥이 부족한데도 무조건 loop를 켜기

설치 기본 모드는 아래 셋 중 첫 번째여야 한다.

- `install only`
- `install + dry-run`
- `install + run-once`

무한 iteration loop는 opt-in으로만 제공한다.

---

## 14. Scripts Scope

이 프로젝트는 문서만 제공하는 저장소가 아니다. 최종적으로는 아래 canonical 스크립트 구현을 포함해야 한다.

- `scripts/_utils.py`
- `scripts/gen-bridges.py`
- `scripts/gen-docs-diff.py`
- `scripts/run-phases.py`
- `scripts/run-server.py`
- `.agent-harness/skills/*`
- `.agent-harness/roles/*`
- `.agent-harness/providers/*`
- `.agent-harness/prompts/*`

즉 installer는 "설계만 적힌 문서"가 아니라, **이 canonical implementation을 타겟 레포에 설치하게 만드는 문서**여야 한다.

---

## 15. Current Known Gap

현재 구현은 canonical 구조를 갖춘 초안이다. 남은 갭은 아래와 같다.

- 실제 Claude/Codex CLI 버전별 end-to-end 실행 검증이 아직 필요함
- installer는 기본적으로 `https://github.com/Ssoon-m/phaseloop.git`에서 canonical core를 가져오며, 로컬 개발 시 `HARNESS_SOURCE`로 override할 수 있음
- provider별 capability matrix를 실제 help output 기반으로 더 구체화해야 함
- role output schema는 `decision_v1`만 정의되어 있고 확장/버전 관리 정책이 더 필요함
- generated bridge 파일의 overwrite/merge 정책을 테스트 fixture로 검증해야 함

따라서 다음 작업 우선순위는 아래로 둔다.

1. local install fixture로 core 복사와 bridge 생성 검증
2. provider별 CLI help 기반 capability matrix 보강
3. role output schema versioning 보강
4. installer merge safety 개선
5. 실제 Claude/Codex headless smoke run

---

## 16. Session Resume Note

세션을 껐다가 다시 켰을 때는 이 파일을 먼저 읽고 아래 사실을 기준으로 이어간다.

- 목표는 **설치형 하네스 표준**
- 핵심은 **canonical core + installer documents**
- Claude 종속 이름은 줄이고 `.agent-harness/` 중심으로 이동
- skill은 `.agent-harness/skills`를 source of truth로 두고 런타임별 bridge를 생성
- subagent는 직접 공유하지 말고 `.agent-harness/roles`에서 Claude/Codex bridge를 생성
- Codex도 **무인 실행** 가능해야 하며 사용자 승인에 기대면 안 됨
- installer는 생성기보다 **표준 설치기**여야 함
