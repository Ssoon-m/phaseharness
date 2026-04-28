# SPEC

## 1. Purpose

phaseloop는 Claude Code와 Codex에서 함께 사용할 수 있는 설치형 agent workflow harness다.

목표는 특정 런타임의 대화 기억에 기대지 않고, 명시적인 작업 요청을 파일 기반 artifact pipeline으로 실행하는 것이다.

기본 실행 모델은 main-session clarify와 balanced headless sessions다. 현재
대화 세션은 `clarify`를 수행해 사용자와 필요한 질문을 주고받고, 이후 작업은
`analysis`, `build`, `evaluate` headless agent session으로 분리한다.

핵심 사용 시나리오:

1. 사용자가 타겟 레포에서 Claude Code 또는 Codex 세션을 연다.
2. 사용자가 installer URL을 에이전트에게 준다.
3. 에이전트가 이 저장소의 canonical core를 타겟 레포에 설치한다.
4. 사용자는 `phaseloop` skill 또는 `scripts/run-workflow.py`로 작업을 실행한다.
5. 사용자가 선택한 commit mode에 따라 성공한 workflow 결과를 commit한다. 기본값은 `none`이다.

## 2. Non-goals

- 타겟 레포마다 새 harness를 즉석 설계하는 것
- `.claude/` 또는 `.codex/`를 canonical source로 삼는 것
- Claude/Codex native subagent 포맷을 하나로 통합하는 것
- 무한 실행 루프를 제공하는 것
- context가 부족해도 무조건 진행하는 것
- interactive approval UI에 의존하는 것

## 3. Canonical Model

canonical source는 `.agent-harness/` 아래에 있다.

안정적인 계약은 아래 파일들이다.

- `tasks/index.json`
- `tasks/<task-dir>/index.json`
- `tasks/<task-dir>/artifacts/01-clarify.md`
- `tasks/<task-dir>/artifacts/02-context.md`
- `tasks/<task-dir>/artifacts/03-plan.md`
- `tasks/<task-dir>/artifacts/04-generate.md`
- `tasks/<task-dir>/artifacts/05-evaluate.md`
- `tasks/<task-dir>/phase<N>.md`
- `tasks/<task-dir>/analysis-output-attempt<N>.json`
- `tasks/<task-dir>/phase<N>-output.json`
- `tasks/<task-dir>/generate-output.json`
- `tasks/<task-dir>/evaluate-output-attempt<N>.json`
- `tasks/<task-dir>/index.json`의 `git_baseline`
- `tasks/<task-dir>/index.json`의 optional `commit`

대화 context는 계약이 아니다. 다음 단계는 이전 단계의 artifact 파일을 읽고 진행해야 한다.

## 4. Repository Layout

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
      .gitignore
      skills/
        phaseloop/
        commit/
      roles/
        phase-clarify/
        phase-context/
        phase-plan/
        phase-generate/
        phase-evaluate/
      prompts/
        task-create.md
      providers/
    scripts/
      _utils.py
      gen-bridges.py
      gen-docs-diff.py
      install-hooks.py
      commit-result.py
      run-phases.py
      run-workflow.py
      sync-bridges.py
    templates/
      docs/
```

## 5. Target Repository Layout

설치 후 타겟 레포는 아래 구조를 갖는다.

```text
<target_repo>/
  .agent-harness/
    config.toml
    .gitignore
    skills/
      phaseloop/
      commit/
    roles/
      phase-clarify/
      phase-context/
      phase-plan/
      phase-generate/
      phase-evaluate/
    prompts/
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
    install-hooks.py
    commit-result.py
    run-phases.py
    run-workflow.py
    sync-bridges.py
  docs/
    mission.md
    spec.md
    testing.md
    user-intervention.md
  tasks/
    .gitignore
    index.json

  .claude/
    skills/ -> ../.agent-harness/skills
    hooks/
      phaseloop-sync-bridges.sh
    agents/
      phase-clarify.md
      phase-context.md
      phase-plan.md
      phase-generate.md
      phase-evaluate.md
  .agents/
    skills/ -> ../.agent-harness/skills
  .codex/
    hooks/
      phaseloop-sync-bridges.sh
    agents/
      phase-clarify.toml
      phase-context.toml
      phase-plan.toml
      phase-generate.toml
      phase-evaluate.toml
```

`.claude/`, `.agents/`, `.codex/`의 phaseloop bridge 파일은 generated bridge다. 직접 수정 대상이 아니다. 기존 사용자 hook 설정은 보존해야 하며, phaseloop가 관리하는 hook entry만 추가 또는 교체한다.

## 6. Workflow

phaseloop의 실행 단위는 명시적인 작업 요청이다.

```bash
AGENT_HEADLESS=1 python3 scripts/run-workflow.py "Implement <small request>" --clarify-file tasks/.phaseloop-clarify.md --provider codex --max-attempts 2 --session-timeout-sec 600
```

또는 에이전트 세션에서:

```text
Use the phaseloop skill to implement <small request>.
```

실행 순서:

1. `clarify`: 현재 대화에서 사용자 요구사항을 이해하고 필요한 질문, 사용자 결정, goal, done condition, assumption, non-goal을 정리한다.
2. `context gather`: 참고해야 할 문서, 코드, 패턴, 제약을 찾는다.
3. `plan`: task index와 phase 파일을 생성한다.
4. `generate`: phase 파일을 순서대로 실행하고 구현한다.
5. `evaluate`: done condition과 acceptance criteria를 검증한다.
6. optional `commit`: 사용자가 `final` 또는 `phase` commit mode를 선택한 경우 완료된 결과를 git commit으로 남긴다.

기본 에이전트 세션 경계는 logical phase와 1:1이 아니다.

- `clarify` main session: 사용자와 핑퐁하며 `artifacts/01-clarify.md` 입력 파일을 만든다.
- `analysis` session: `context gather`, `plan`을 한 headless agent session에서 수행한다.
- `build` session(s): `phase<N>.md` 구현 phase를 수행한다.
- `evaluate` session: 구현 세션과 분리된 headless agent session에서 검증한다.

이 전략은 요구사항의 애매한 부분을 사용자-facing 대화에서 정리하면서도, 이후
탐색 대화가 구현/검증 context에 계속 쌓이는 것을 막고 작은 logical phase마다
AGENTS.md 같은 runtime startup context를 반복 로드하는 비용을 줄인다.

표준 결과는 항상 artifact 파일이다. native subagent bridge는 interactive convenience일 수 있지만 lifecycle correctness의 기준은 아니다.

성공 후 commit은 workflow의 기본 단계가 아니다. 기본 commit mode는 `none`이며, phaseloop skill은 실행 전에 `none`, `final`, `phase` 중 하나를 확인해야 한다.

commit mode:

- `none`: 자동 commit을 만들지 않는다.
- `final`: evaluation이 `pass` 또는 `warn`이면 workflow 마지막에 commit 하나를 만든다.
- `phase`: 완료된 generate phase마다 commit을 만든다. evaluation은 local task state로만 남기며 빈 validation commit을 만들지 않는다.

자동 product commit은 기본적으로 `tasks/<task-dir>/artifacts/*` 같은 phaseloop state 파일을 포함하지 않는다. commit subject는 작업 요청 또는 phase metadata의 `commit_message`를 사용한다. 설치된 타겟 레포는 `tasks/.gitignore`로 runtime task state를 기본 ignore한다. phaseloop state 파일을 commit해야 할 때는 사용자가 명시적으로 `--include-harness-state`를 선택해야 한다.
커밋할 product change가 없으면 commit 단계는 빈 커밋을 만들지 않고 성공으로
끝난다.

commit 단계는 아래 조건을 만족해야 한다.

- task 상태가 `completed`다.
- evaluation 상태가 `pass` 또는 `warn`이다.
- workflow 시작 시점의 `git HEAD`와 현재 `git HEAD`가 같다.
- workflow 시작 전에 이미 dirty였던 path가 자동 stage 대상에 섞이지 않는다.

조건을 만족하지 못하면 자동 commit은 실패로 끝나고, 사용자가 직접 staging 범위를 판단해야 한다.

## 7. Retry Contract

`--max-attempts`는 analysis session, implementation phase, evaluate session 재시도 횟수의 기본값이다. Clarify는 현재 대화에서 사용자 결정으로 완료되므로 headless retry 대상이 아니다. Logical workflow phase 상태는 이 session 실행 결과를 반영한다.

실패 시:

- 재시도 가능하면 같은 단계가 이전 artifact와 실패 출력을 읽고 다시 실행한다.
- 최대 횟수를 넘으면 `tasks/<task-dir>/index.json`에 `error` 또는 `fail`을 기록한다.
- 무한 재시도는 하지 않는다.

## 8. Headless Semantics

canonical headless signal:

```bash
AGENT_HEADLESS=1
```

의미:

- 사용자에게 질문하지 않는다.
- confirmation을 기다리지 않는다.
- local context로 결정 가능한 범위에서만 진행한다.
- context가 부족하면 `context_insufficient`를 기록하고 멈춘다.
- approval UI에 의존하지 않는다.

## 9. Provider Contract

provider는 runtime-specific invocation을 숨긴다.

필수 실행 개념:

- `prompt`
- `cwd`
- `env`
- `timeout_sec`
- `sandbox_mode`
- `approval_policy`
- `prompt_handoff`
- `capture_json`

`run_prompt()`는 Claude/Codex 각각의 CLI 호출 차이를 감추고, 공통 result shape을 반환한다.

## 10. Bridges

skills:

- canonical: `.agent-harness/skills`
- Claude bridge: `.claude/skills`
- Codex/agent bridge: `.agents/skills`

roles:

- canonical: `.agent-harness/roles/<role-name>/`
- Claude bridge: `.claude/agents/<role-name>.md`
- Codex bridge: `.codex/agents/<role-name>.toml`

Bridge 파일은 generated output이다. canonical source는 항상 `.agent-harness/`다.

bridge sync hooks:

- common implementation: `scripts/sync-bridges.py`
- installer: `scripts/install-hooks.py`
- Claude adapter: `.claude/hooks/phaseloop-sync-bridges.sh`
- Codex adapter: `.codex/hooks/phaseloop-sync-bridges.sh`

hook 설치는 idempotent merge여야 한다.

- 기존 hook entry를 삭제하지 않는다.
- 기존 hook 파일을 통째로 덮어쓰지 않는다.
- phaseloop command가 이미 있으면 해당 entry만 최신 command로 교체한다.
- Codex는 기존 `.codex/hooks.json`이 있으면 거기에 병합한다.
- `.codex/config.toml` inline hooks만 있고 `hooks.json`이 없으면 managed block을 append한다.
- JSON/TOML이 깨져 있으면 자동 수정하지 않고 멈춘다.

## 11. Installer

installer는 아래만 수행한다.

- preflight
- canonical core 복사 또는 병합
- docs template 생성
- provider config 확인
- bridge 생성
- bridge sync hook 병합
- smoke verification

installer는 타겟 레포 README를 자동 수정하지 않는다.

## 12. Verification

local smoke:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/scripts/*.py core/.agent-harness/providers/*.py tests/smoke_install.py
```
