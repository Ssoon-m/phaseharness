#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from _utils import find_project_root, git, git_head, load_config, load_json, load_provider, now_iso, save_json


def log(message: str) -> None:
    print(f"[phaseloop] {message}", flush=True)


def is_harness_state_path(path: str) -> bool:
    return path == "tasks" or path == "tasks/" or path.startswith("tasks/")


def git_status_paths(root: Path) -> set[str]:
    result = git("status", "--porcelain=v1", "-z", root=root, check=True)
    paths: set[str] = set()
    chunks = result.stdout.split("\0")
    i = 0
    while i < len(chunks):
        raw = chunks[i]
        i += 1
        if not raw or len(raw) < 4:
            continue
        code = raw[:2]
        paths.add(raw[3:])
        if "R" in code or "C" in code:
            if i < len(chunks) and chunks[i]:
                paths.add(chunks[i])
                i += 1
    return paths


def pending_product_paths(root: Path, task_dir: Path) -> list[str]:
    index = load_json(task_dir / "index.json")
    baseline = index.get("git_baseline", {})
    dirty_paths = baseline.get("dirty_paths", []) if isinstance(baseline, dict) else []
    baseline_dirty_paths = set(dirty_paths) if isinstance(dirty_paths, list) else set()
    return sorted(
        path
        for path in git_status_paths(root) - baseline_dirty_paths
        if not is_harness_state_path(path)
    )


def build_phase_commit_prompt(root: Path, task_dir: Path, phase: dict[str, Any]) -> str:
    phase_num = phase["phase"]
    phase_file = task_dir / f"phase{phase_num}.md"
    phase_content = phase_file.read_text() if phase_file.exists() else ""
    task_index = (task_dir / "index.json").read_text()
    commit_skill = (root / ".agent-harness" / "skills" / "commit" / "SKILL.md").read_text()
    headless_commit = (root / ".agent-harness" / "skills" / "commit" / "references" / "headless.md").read_text()
    message_guidance = (root / ".agent-harness" / "skills" / "commit" / "references" / "message-guidance.md").read_text()
    commit_message = str(phase.get("commit_message") or "").strip()
    return f"""Run the phaseloop phase-local commit step.

## Commit Skill

{commit_skill}

## Headless Commit Rules

{headless_commit}

## Commit Message Guidance

{message_guidance}

## Invocation

- Phase: {phase_num}
- Preferred commit message: `{commit_message or "no phase commit_message was provided"}`
- Task directory: `{task_dir.relative_to(root)}`

## Task Index

```json
{task_index}
```

## Phase File

```markdown
{phase_content}
```
"""


def commit_phase_result(
    root: Path,
    task_dir: Path,
    phase: dict[str, Any],
    provider: Any,
    commit_mode: str,
    timeout: int,
    sandbox_mode: str,
    approval_policy: str,
    prompt_handoff: str,
) -> int:
    if commit_mode != "phase":
        return 0
    phase_num = int(phase["phase"])
    if not pending_product_paths(root, task_dir):
        log(f"phase {phase_num} has no product file changes to commit")
        return 0
    before = git_head(root)
    log(f"commit-mode=phase session=commit phase={phase_num} timeout={timeout}s task={task_dir.name}")
    result = provider.run_prompt(
        build_phase_commit_prompt(root, task_dir, phase),
        cwd=str(root),
        timeout_sec=timeout,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        prompt_handoff=prompt_handoff,
        capture_json=True,
    )
    save_json(
        task_dir / f"phase{phase_num}-commit-output.json",
        {
            "phase": phase_num,
            "provider": provider.name,
            **result,
        },
    )
    if result["exit_code"] != 0:
        return int(result["exit_code"])
    after = git_head(root)
    if after == before:
        log(f"phase {phase_num} commit was not created")
        return 0
    log(f"phase {phase_num} committed {after[:12]}")
    return 0


def find_next_phase(index: dict[str, Any]) -> dict[str, Any] | None:
    for phase in index.get("phases", []):
        if phase.get("status") == "pending":
            return phase
    return None


def update_top_index(root: Path, task_dir_name: str, status: str) -> None:
    top_index_path = root / "tasks" / "index.json"
    if not top_index_path.exists():
        return
    data = load_json(top_index_path, {"tasks": []})
    for task in data.get("tasks", []):
        if task.get("dir") == task_dir_name:
            task["status"] = status
            if status == "completed":
                task["completed_at"] = now_iso()
            elif status == "error":
                task["failed_at"] = now_iso()
            break
    save_json(top_index_path, data)


def set_phase_field(index: dict[str, Any], phase_num: int, **fields: Any) -> None:
    for phase in index.get("phases", []):
        if phase.get("phase") == phase_num:
            phase.update(fields)
            return


def read_role_prompt(root: Path, role_name: str) -> str:
    return (root / ".agent-harness" / "roles" / role_name / "prompt.md").read_text()


def read_artifact_if_exists(task_dir: Path, rel: str) -> str:
    path = task_dir / rel
    return path.read_text() if path.exists() else ""


def configured_attempts(config: dict[str, Any], key: str, default: int) -> int:
    execution = config.get("execution", {})
    if not isinstance(execution, dict):
        return default
    try:
        return max(1, int(execution.get(key, default)))
    except (TypeError, ValueError):
        return default


def phase_max_attempts(config: dict[str, Any], phase: dict[str, Any]) -> int:
    value = phase.get("max_attempts")
    if value is None:
        return configured_attempts(config, "phase_max_attempts", 1)
    try:
        attempts = int(value)
    except (TypeError, ValueError):
        return configured_attempts(config, "phase_max_attempts", 1)
    if attempts < 1:
        return configured_attempts(config, "phase_max_attempts", 1)
    return attempts


def ensure_generate_artifact(task_dir: Path) -> None:
    artifact = task_dir / "artifacts" / "04-generate.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if not artifact.exists():
        artifact.write_text("# Phase 4: Generate\n\n")


def build_phase_prompt(root: Path, task_dir: Path, phase: dict[str, Any], attempt: int, max_attempts: int) -> str:
    phase_num = phase["phase"]
    phase_file = task_dir / f"phase{phase_num}.md"
    if not phase_file.exists():
        raise FileNotFoundError(phase_file)
    phase_content = phase_file.read_text()
    task_index = (task_dir / "index.json").read_text()
    generate_role = read_role_prompt(root, "phase-generate")
    artifacts = []
    for rel in (
        "artifacts/01-clarify.md",
        "artifacts/02-context.md",
        "artifacts/03-plan.md",
        "artifacts/04-generate.md",
    ):
        content = read_artifact_if_exists(task_dir, rel)
        if content:
            artifacts.append(f"## {task_dir.relative_to(root)}/{rel}\n\n{content}")
    artifacts_text = "\n\n".join(artifacts) if artifacts else "No prior artifacts found."
    return f"""Run the phaseloop build session for one planned generate phase.

Workflow invariant: `clarify -> context -> plan -> generate -> evaluate` is fixed.
`run-phases` performs the build session (`generate`) from existing task artifacts
and phase files; do not restart clarify, context, or planning.

{generate_role}

## Invocation

- Task directory: `{task_dir.relative_to(root)}`
- Phase: {phase_num}
- Attempt: {attempt} of {max_attempts}
- Runtime: headless; do not ask questions.

## Task Index

```json
{task_index}
```

## Prior Artifacts

{artifacts_text}

## Phase Content

{phase_content}
"""


def run_docs_diff(root: Path, task_dir: Path, baseline: str) -> None:
    subprocess.run(
        ["python3", str(root / "scripts" / "gen-docs-diff.py"), str(task_dir), baseline],
        cwd=str(root),
        check=False,
    )


def run_phases(
    task_dir_name: str,
    provider_name: str | None = None,
    max_attempts_override: int | None = None,
    session_timeout_sec: int | None = None,
    commit_mode: str = "none",
) -> int:
    root = find_project_root()
    config = load_config(root)
    provider = load_provider(provider_name, root)
    task_dir = root / "tasks" / task_dir_name
    index_path = task_dir / "index.json"
    if not index_path.exists():
        print(f"missing task index: {index_path}")
        return 1

    baseline = git_head(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    timeout = session_timeout_sec or int(execution.get("session_timeout_sec", execution.get("phase_timeout_sec", 1800)))
    sandbox_mode = str(config.get("execution", {}).get("sandbox_mode", "workspace-write"))
    approval_policy = str(config.get("execution", {}).get("approval_policy", "never"))
    prompt_handoff = str(config.get("execution", {}).get("prompt_handoff", "stdin"))

    while True:
        index = load_json(index_path)
        phase = find_next_phase(index)
        if phase is None:
            index = load_json(index_path)
            index["completed_at"] = now_iso()
            index["status"] = "completed"
            save_json(index_path, index)
            update_top_index(root, task_dir_name, "completed")
            log(f"all phases completed: {task_dir_name}")
            return 0

        phase_num = int(phase["phase"])
        max_attempts = max_attempts_override or phase_max_attempts(config, phase)
        attempt = int(phase.get("attempts", 0)) + 1
        set_phase_field(
            index,
            phase_num,
            status="running",
            started_at=phase.get("started_at", now_iso()),
            attempts=attempt,
            max_attempts=max_attempts,
        )
        save_json(index_path, index)

        ensure_generate_artifact(task_dir)
        log(f"session=build phase={phase_num} attempt={attempt}/{max_attempts} timeout={timeout}s task={task_dir_name}")
        prompt = build_phase_prompt(root, task_dir, phase, attempt, max_attempts)
        result = provider.run_prompt(
            prompt,
            cwd=str(root),
            timeout_sec=timeout,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            prompt_handoff=prompt_handoff,
            capture_json=True,
        )
        output_path = task_dir / f"phase{phase_num}-output.json"
        save_json(
            output_path,
            {
                "phase": phase_num,
                "name": phase.get("name"),
                "provider": provider.name,
                **result,
            },
        )

        fresh_index = load_json(index_path)
        fresh_phase = next(
            (p for p in fresh_index.get("phases", []) if p.get("phase") == phase_num),
            None,
        )
        status = fresh_phase.get("status", "pending") if fresh_phase else "pending"
        if status == "completed":
            set_phase_field(fresh_index, phase_num, completed_at=now_iso())
            save_json(index_path, fresh_index)
            if phase_num == 0:
                run_docs_diff(root, task_dir, baseline)
            commit_code = commit_phase_result(
                root,
                task_dir,
                fresh_phase or phase,
                provider,
                commit_mode,
                timeout,
                sandbox_mode,
                approval_policy,
                prompt_handoff,
            )
            if commit_code != 0:
                update_top_index(root, task_dir_name, "error")
                log(f"phase {phase_num} commit failed")
                return commit_code
            log(f"phase {phase_num} completed")
            continue

        failure = result["failure_category"] or "runtime_error"
        if attempt < max_attempts:
            set_phase_field(
                fresh_index,
                phase_num,
                status="pending",
                last_failure_at=now_iso(),
                last_error_message=f"{failure}: retrying phase",
            )
            save_json(index_path, fresh_index)
            log(f"phase {phase_num} retrying ({attempt}/{max_attempts})")
            continue

        if status != "error":
            set_phase_field(
                fresh_index,
                phase_num,
                status="error",
                failed_at=now_iso(),
                error_message=f"{failure}: phase did not mark itself completed",
            )
            save_json(index_path, fresh_index)

        update_top_index(root, task_dir_name, "error")
        log(f"phase {phase_num} failed")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed workflow build session from planned phase files.")
    parser.add_argument("task_dir", help="Task directory name under tasks/")
    parser.add_argument("--provider", default=None, help="Provider name override")
    parser.add_argument("--max-attempts", type=int, default=None, help="Retry attempts per phase")
    parser.add_argument("--session-timeout-sec", type=int, default=None, help="Timeout for each workflow session or build phase call")
    parser.add_argument("--phase-timeout-sec", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--commit-mode", choices=["none", "phase"], default="none", help="Commit mode for completed implementation phases")
    args = parser.parse_args()
    session_timeout_sec = args.session_timeout_sec or args.phase_timeout_sec
    return run_phases(args.task_dir, args.provider, args.max_attempts, session_timeout_sec, args.commit_mode)


if __name__ == "__main__":
    raise SystemExit(main())
