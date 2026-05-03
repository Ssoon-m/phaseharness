# phaseloop

Claude Code와 Codex에서 사용할 수 있는 설치형 `phaseharness` workflow입니다.

이 저장소는 대상 repository에 `.phaseharness/` 디렉터리로 복사되는 canonical
harness를 제공합니다. 설치된 harness는 provider의 `SessionStart` hook으로
bridge 파일을 다시 동기화하고, `Stop` hook과 파일 상태로 하나의 작업을 아래
순서로 진행합니다.

```text
clarify -> context gather -> plan -> generate -> evaluate
```

Stop hook은 provider 설정에 설치되지만 기본적으로 비활성입니다. 사용자가
`phaseharness` skill을 명시적으로 호출하고 skill이 active run 파일을 만들 때만
loop가 이어집니다.

## 설치

대상 저장소에서 Claude Code 또는 Codex를 열고 아래 요청을 전달합니다.

```text
Install phaseharness from this installer document:
https://github.com/Ssoon-m/phaseloop/blob/main/installer/install-harness.md
```

Installer는 `core/.phaseharness/`를 대상 저장소의 `.phaseharness/`로 복사하고,
Claude/Codex `SessionStart`와 `Stop` hook entry, `phaseharness` skill bridge,
provider-native subagent bridge를 설치한 뒤 smoke verification을 실행합니다.

## 작업 실행

설치된 skill을 명시적으로 사용합니다.

```text
Use the phaseharness skill to implement <request> with loop count 2, max attempts per phase 2, and commit mode none.
```

Loop count, max attempts per phase, commit mode가 빠져 있으면 skill은 active
run을 만들기 전에 한 번 질문해야 합니다. Loop count는 `generate -> evaluate`
cycle의 최대 횟수이고, max attempts per phase는 plan에서 나뉜 각 implementation
phase의 retry budget입니다. Commit mode는 `none`, `final`, `phase` 중
하나입니다.

## 실행 옵션

`loop count`는 전체 build-review cycle의 최대 횟수입니다. 한 loop에서는 계획된
implementation phase를 `generate`가 처리하고, `evaluate`가 `pass`, `warn`,
`fail`을 판정합니다. `evaluate`가 실패하고 follow-up phase 파일을 추가하면 다음
loop에서 다시 `generate`로 돌아갑니다. `loop count 2`는 첫 평가 실패 뒤 한 번의
추가 build-review cycle을 허용한다는 뜻입니다.

`max attempts per phase`는 각 실행 phase의 retry budget입니다. `generate`에서는
`phase-001`, `phase-002` 같은 계획된 implementation phase마다 따로 적용됩니다.
전체 workflow를 처음부터 다시 시작하는 횟수가 아닙니다.

`commit mode`는 product commit 생성 방식을 정합니다.

- `none`: 자동 commit을 만들지 않습니다.
- `phase`: 계획된 implementation phase가 완료될 때마다 product change를 commit합니다.
- `final`: `evaluate`가 `pass` 또는 `warn`이면 product commit 하나를 만듭니다.

Commit helper는 기본적으로 `.phaseharness/` runtime state와 provider bridge
파일을 product commit에서 제외합니다.

일반 질문, 짧은 설명, 리뷰, 단발성 명령은 loop를 활성화하지 않습니다.
Activation은 `.phaseharness/state/active.json`에
`activation_source: "phaseharness_skill"`이 있을 때만 성립합니다.

대화가 끊기면 다음 세션에서 `phaseharness` skill을 다시 호출해 active run을
이어가라고 요청합니다. Resume도 명시적이어야 하므로 새 세션의 일반 질문이
loop를 다시 시작하지 않습니다.

## State 위치

Canonical harness 파일과 runtime state는 모두 `.phaseharness/` 아래에 둡니다.

- `.phaseharness/bin/`: state, hook, bridge sync, commit helper
- `.phaseharness/hooks/`: provider hook wrapper
- `.phaseharness/skills/phaseharness/`: skill 지침
- `.phaseharness/subagents/`: phase별 subagent 지침
- `.phaseharness/runs/`: run별 artifact와 state
- `.phaseharness/state/`: active run pointer와 run index

`.phaseharness/` SSOT 기준으로 provider bridge 파일을 다시 맞추려면 다음을
실행합니다.

```bash
python3 .phaseharness/bin/phaseharness-sync-bridges.py
```

설치된 `SessionStart` hook도 세션 시작/재개 시 같은 bridge sync를 조용히
실행합니다. 그래서 `.phaseharness/subagents/*.md`,
`.phaseharness/skills/phaseharness/`, `.phaseharness/config.toml`을 수정하면
provider bridge 파일에 세션 시작 전에 반영됩니다.

`.phaseharness/` 밖에 남는 파일은 provider가 요구하는 hook entry, skill symlink,
provider-native subagent bridge뿐입니다.

- `.claude/settings.json`
- `.codex/config.toml`
- `.codex/hooks.json` 또는 Codex inline hook config
- `.claude/skills/phaseharness`
- `.agents/skills/phaseharness`
- `.claude/agents/phaseharness-*.md`
- `.codex/agents/phaseharness-*.toml`

## Subagent 동작

Phaseharness는 provider-native subagent bridge 파일을 설치합니다. Provider
hook은 shell command로 실행되므로 hook 자체가 provider subagent API를 호출할
수는 없습니다. 대신 Stop hook이 반환하는 continuation prompt의 첫 필수 동작을
phase별 subagent 직접 호출로 고정합니다.

- Claude Code: `phaseharness-clarify`, `phaseharness-context-gather`,
  `phaseharness-plan`, `phaseharness-generate`, `phaseharness-evaluate`
- Codex: `phaseharness_clarify`, `phaseharness_context_gather`,
  `phaseharness_plan`, `phaseharness_generate`, `phaseharness_evaluate`

Parent conversation은 phase 작업을 직접 수행하지 않습니다. provider가
Stop-hook continuation에서 subagent를 실행할 수 없으면 local fallback을 하지
않고 `subagent_unavailable` 오류로 run을 `waiting_user` 상태로 둡니다.

## 권한 동작

`.phaseharness/config.toml`이 관리 대상 provider 권한의 SSOT입니다. 권한
table은 가능한 provider native key 모양을 그대로 따릅니다.

- `[permissions.claude.settings.permissions]`는 `.claude/settings.json`의
  `permissions`로 매핑됩니다.
- `[permissions.claude.subagents]`는 Claude Code subagent frontmatter로
  매핑됩니다.
- `[permissions.codex.config]`는 Codex config/custom-agent의
  `approval_policy`, `sandbox_mode`, `sandbox_workspace_write.*` 같은 key로
  매핑됩니다.

기본 profile은 loop 중 매 phase마다 권한 확인으로 멈추지 않도록 넓게 열려
있습니다.

이 설정은 의도적으로 넓습니다. 반복 승인 없이 provider가 project command와
파일 수정을 수행해도 되는 repository에만 phaseharness를 설치하세요.
설치 후 더 보수적인 동작을 원하면 `.phaseharness/config.toml`에서 권한 설정을
낮추고 bridge sync command를 다시 실행하면 됩니다.

## 개발

로컬 검증:

```bash
python3 tests/smoke_install.py
python3 -m py_compile core/.phaseharness/bin/*.py tests/smoke_install.py
```

구현 세부사항은 `SPEC.md`와 `spec/`를 참고하세요.
