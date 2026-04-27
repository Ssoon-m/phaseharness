#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from _utils import find_project_root, git_head, load_config, load_json, load_provider, now_iso, save_json


def log(message: str) -> None:
    print(f"[phaseloop] {message}", flush=True)


def commit_phase_result(root: Path, task_dir_name: str, phase_num: int, commit_mode: str) -> int:
    if commit_mode != "phase":
        return 0
    cmd = [
        sys.executable,
        str(root / "scripts" / "commit-result.py"),
        task_dir_name,
        "--phase",
        str(phase_num),
        "--allow-head-move",
    ]
    log(f"commit-mode=phase command={' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(root), text=True)
    return result.returncode


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
    docs = []
    for rel in ("docs/mission.md", "docs/spec.md", "docs/testing.md", "docs/user-intervention.md"):
        path = root / rel
        if path.exists():
            docs.append(f"## {rel}\n\n{path.read_text()}")
    docs_text = "\n\n".join(docs) if docs else "No project docs found."
    artifacts_text = "\n\n".join(artifacts) if artifacts else "No prior artifacts found."
    return f"""You are executing one harness phase in an independent session.

{generate_role}

Headless mode:
- If AGENT_HEADLESS=1, do not ask questions.
- Run the acceptance criteria commands yourself when possible.
- Update `{task_dir.relative_to(root)}/index.json` with the final phase status.
- Use `context_insufficient`, `validation_failed`, `sandbox_blocked`, or `runtime_error` in `error_message` when failing.

Attempt:
- This is attempt {attempt} of {max_attempts}.
- If this attempt cannot complete after reasonable local fixes, record `error`.

## Task Index

```json
{task_index}
```

## Prior Artifacts

{artifacts_text}

## Project Docs

{docs_text}

## Phase Content

{phase_content}
"""


def run_docs_diff(root: Path, task_dir: Path, baseline: str) -> None:
    subprocess.run(
        ["python3", str(root / "scripts" / "gen-docs-diff.py"), str(task_dir), baseline],
        cwd=str(root),
        check=False,
    )


def build_evaluation_prompt(root: Path, task_dir: Path, attempt: int, max_attempts: int) -> str:
    evaluate_role = read_role_prompt(root, "phase-evaluate")
    task_index = (task_dir / "index.json").read_text()
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
    docs = []
    for rel in ("docs/mission.md", "docs/spec.md", "docs/testing.md", "docs/user-intervention.md"):
        path = root / rel
        if path.exists():
            docs.append(f"## {rel}\n\n{path.read_text()}")
    return f"""You are executing the final evaluation phase in an independent session.

{evaluate_role}

Headless mode:
- If AGENT_HEADLESS=1, do not ask questions.
- Fix local validation errors when the fix is clearly in scope.
- Write `{task_dir.relative_to(root)}/artifacts/05-evaluate.md`.
- Update `{task_dir.relative_to(root)}/index.json` evaluation status.

Attempt:
- This is evaluation attempt {attempt} of {max_attempts}.

## Task Index

```json
{task_index}
```

## Artifacts

{chr(10).join(artifacts) if artifacts else "No prior artifacts found."}

## Project Docs

{chr(10).join(docs) if docs else "No project docs found."}
"""


def run_evaluation(
    root: Path,
    task_dir: Path,
    provider: Any,
    config: dict[str, Any],
    provider_name: str | None,
    max_attempts_override: int | None = None,
    timeout_sec_override: int | None = None,
) -> int:
    del provider_name
    index_path = task_dir / "index.json"
    index = load_json(index_path)
    evaluation = index.get("evaluation", {})
    if not isinstance(evaluation, dict):
        evaluation = {}
    status = evaluation.get("status")
    if status in ("pass", "warn"):
        return 0

    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    max_attempts = max_attempts_override or int(
        evaluation.get("max_attempts") or configured_attempts(config, "evaluation_max_attempts", 1)
    )
    timeout = timeout_sec_override or int(execution.get("check_timeout_sec", 600))
    sandbox_mode = str(execution.get("sandbox_mode", "workspace-write"))
    approval_policy = str(execution.get("approval_policy", "never"))
    prompt_handoff = str(execution.get("prompt_handoff", "stdin"))

    for attempt in range(int(evaluation.get("attempts", 0)) + 1, max_attempts + 1):
        log(f"session=evaluate attempt={attempt}/{max_attempts} timeout={timeout}s task={task_dir.name}")
        index = load_json(index_path)
        evaluation = index.get("evaluation", {})
        if not isinstance(evaluation, dict):
            evaluation = {}
        evaluation.update({"status": "running", "attempts": attempt, "max_attempts": max_attempts})
        index["evaluation"] = evaluation
        save_json(index_path, index)

        result = provider.run_prompt(
            build_evaluation_prompt(root, task_dir, attempt, max_attempts),
            cwd=str(root),
            timeout_sec=timeout,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            prompt_handoff=prompt_handoff,
            capture_json=True,
        )
        save_json(
            task_dir / f"evaluation-output-attempt{attempt}.json",
            {
                "attempt": attempt,
                "provider": provider.name,
                **result,
            },
        )

        fresh = load_json(index_path)
        fresh_eval = fresh.get("evaluation", {})
        fresh_status = fresh_eval.get("status") if isinstance(fresh_eval, dict) else None
        if fresh_status in ("pass", "warn"):
            log(f"session=evaluate completed status={fresh_status}")
            return 0
        if attempt < max_attempts:
            log(f"session=evaluate retrying status={fresh_status or 'unknown'}")
            continue

    index = load_json(index_path)
    evaluation = index.get("evaluation", {})
    if not isinstance(evaluation, dict):
        evaluation = {}
    evaluation.update(
        {
            "status": "fail",
            "failed_at": now_iso(),
            "error_message": "evaluation did not pass within max_attempts",
        }
    )
    index["evaluation"] = evaluation
    save_json(index_path, index)
    log("session=evaluate failed")
    return 1


def run_phases(
    task_dir_name: str,
    provider_name: str | None = None,
    max_attempts_override: int | None = None,
    skip_evaluation: bool = False,
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
            if not skip_evaluation and run_evaluation(root, task_dir, provider, config, provider_name, max_attempts_override, session_timeout_sec) != 0:
                update_top_index(root, task_dir_name, "error")
                log(f"evaluation failed: {task_dir_name}")
                return 1
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
            commit_code = commit_phase_result(root, task_dir_name, phase_num, commit_mode)
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
    parser = argparse.ArgumentParser(description="Run pending phases for a harness task.")
    parser.add_argument("task_dir", help="Task directory name under tasks/")
    parser.add_argument("--provider", default=None, help="Provider name override")
    parser.add_argument("--max-attempts", type=int, default=None, help="Retry attempts per phase and evaluation")
    parser.add_argument("--session-timeout-sec", type=int, default=None, help="Timeout for each headless agent session or build phase call")
    parser.add_argument("--phase-timeout-sec", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--commit-mode", choices=["none", "phase"], default="none", help="Commit mode for completed implementation phases")
    parser.add_argument("--skip-evaluation", action="store_true", help="Do not run the final evaluation step")
    args = parser.parse_args()
    session_timeout_sec = args.session_timeout_sec or args.phase_timeout_sec
    return run_phases(args.task_dir, args.provider, args.max_attempts, args.skip_evaluation, session_timeout_sec, args.commit_mode)


if __name__ == "__main__":
    raise SystemExit(main())
