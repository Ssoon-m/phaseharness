#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from _utils import ensure_base_state, find_project_root, git, git_head, load_config, load_json, load_provider, now_iso, save_json


ARTIFACT_AGENT_PHASES = [
    ("clarify", "phase-clarify", "artifacts/01-clarify.md"),
    ("context", "phase-context", "artifacts/02-context.md"),
    ("plan", "phase-plan", "artifacts/03-plan.md"),
    ("evaluate", "phase-evaluate", "artifacts/05-evaluate.md"),
]

CLARIFY_PHASE = ARTIFACT_AGENT_PHASES[0]
ANALYSIS_PHASES = ARTIFACT_AGENT_PHASES[1:3]

WORKFLOW_STATUS_PHASES = [
    ("clarify", "artifacts/01-clarify.md"),
    ("context", "artifacts/02-context.md"),
    ("plan", "artifacts/03-plan.md"),
    ("generate", "artifacts/04-generate.md"),
    ("evaluate", "artifacts/05-evaluate.md"),
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "task"


def next_task_number(root: Path) -> int:
    data = load_json(root / "tasks" / "index.json", {"tasks": []})
    max_id = 0
    for item in data.get("tasks", []):
        try:
            max_id = max(max_id, int(item.get("id", 0)))
            continue
        except (TypeError, ValueError):
            pass
        directory = str(item.get("dir", ""))
        prefix = directory.split("-", 1)[0]
        if prefix.isdigit():
            max_id = max(max_id, int(prefix))
    return max_id + 1


def docs_context(root: Path) -> str:
    docs = []
    for rel in ("docs/mission.md", "docs/spec.md", "docs/testing.md", "docs/user-intervention.md"):
        path = root / rel
        if path.exists():
            docs.append(f"## {rel}\n\n{path.read_text()}")
    return "\n\n".join(docs) if docs else "No project docs found."


def role_prompt(root: Path, role_name: str) -> str:
    return (root / ".agent-harness" / "roles" / role_name / "prompt.md").read_text()


def read_existing_artifacts(task_dir: Path) -> str:
    parts = []
    for rel in (
        "artifacts/01-clarify.md",
        "artifacts/02-context.md",
        "artifacts/03-plan.md",
        "artifacts/04-generate.md",
        "artifacts/05-evaluate.md",
    ):
        path = task_dir / rel
        if path.exists():
            parts.append(f"## {rel}\n\n{path.read_text()}")
    return "\n\n".join(parts) if parts else "No prior artifacts found."


def read_artifact_if_exists(task_dir: Path, rel: str) -> str:
    path = task_dir / rel
    return path.read_text() if path.exists() else ""


def workflow_status_template(max_attempts: int) -> list[dict[str, Any]]:
    return [
        {
            "phase": name,
            "artifact": artifact,
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
        }
        for name, artifact in WORKFLOW_STATUS_PHASES
    ]


def session_status_template(max_attempts: int) -> list[dict[str, Any]]:
    return [
        {
            "session": "clarify",
            "phases": ["clarify"],
            "status": "pending",
            "attempts": 0,
            "max_attempts": 1,
        },
        {
            "session": "analysis",
            "phases": ["context", "plan"],
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
        },
        {
            "session": "build",
            "phases": ["generate"],
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
        },
        {
            "session": "evaluate",
            "phases": ["evaluate"],
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
        },
    ]


def log(message: str) -> None:
    print(f"[phaseloop] {message}", flush=True)


def parse_status_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            old_path, new_path = path.split(" -> ", 1)
            paths.extend([old_path, new_path])
        else:
            paths.append(path)
    return sorted(set(paths))


def parse_porcelain_z_paths(status: str) -> list[str]:
    paths: set[str] = set()
    chunks = status.split("\0")
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
    return sorted(paths)


def git_baseline(root: Path) -> dict[str, Any]:
    try:
        head = git_head(root)
    except Exception:
        head = ""
    status_result = git("status", "--short", root=root)
    status = status_result.stdout if status_result.returncode == 0 else ""
    porcelain_result = git("status", "--porcelain=v1", "-z", root=root)
    dirty_paths = (
        parse_porcelain_z_paths(porcelain_result.stdout)
        if porcelain_result.returncode == 0
        else parse_status_paths(status)
    )
    return {
        "head": head,
        "status": status,
        "dirty_paths": dirty_paths,
    }


def create_task(root: Path, request: str, task_name: str, max_attempts: int, session_strategy: str) -> Path:
    ensure_base_state(root)
    task_id = next_task_number(root)
    task_dir_name = f"{task_id}-{slugify(task_name)}"
    task_dir = root / "tasks" / task_dir_name
    (task_dir / "artifacts").mkdir(parents=True, exist_ok=False)

    created_at = now_iso()
    index = {
        "project": root.name,
        "task": task_name,
        "prompt": request,
        "status": "pending",
        "created_at": created_at,
        "done_when": [],
        "max_attempts": max_attempts,
        "session_strategy": session_strategy,
        "git_baseline": git_baseline(root),
        "sessions": session_status_template(max_attempts),
        "workflow": workflow_status_template(max_attempts),
        "artifacts": {
            "clarify": "artifacts/01-clarify.md",
            "context": "artifacts/02-context.md",
            "plan": "artifacts/03-plan.md",
            "generate": "artifacts/04-generate.md",
            "evaluate": "artifacts/05-evaluate.md",
        },
        "phases": [],
        "evaluation": {
            "status": "pending",
            "attempts": 0,
            "max_attempts": max_attempts,
        },
    }
    save_json(task_dir / "index.json", index)

    top = load_json(root / "tasks" / "index.json", {"tasks": []})
    top.setdefault("tasks", []).append(
        {
            "id": task_id,
            "name": task_name,
            "dir": task_dir_name,
            "status": "pending",
            "created_at": created_at,
        }
    )
    save_json(root / "tasks" / "index.json", top)
    return task_dir


def set_workflow_status(task_dir: Path, phase_name: str, **fields: Any) -> None:
    index_path = task_dir / "index.json"
    index = load_json(index_path)
    if not isinstance(index.get("workflow"), list):
        max_attempts = int(index.get("max_attempts", 2))
        index["workflow"] = workflow_status_template(max_attempts)
        for phase in index["workflow"]:
            artifact = task_dir / str(phase.get("artifact", ""))
            if artifact.exists():
                phase["status"] = "completed"
    for phase in index.get("workflow", []):
        if phase.get("phase") == phase_name:
            phase.update(fields)
            break
    save_json(index_path, index)


def set_session_status(task_dir: Path, session_name: str, **fields: Any) -> None:
    index_path = task_dir / "index.json"
    index = load_json(index_path)
    max_attempts = int(index.get("max_attempts", 2))
    if not isinstance(index.get("sessions"), list):
        index["sessions"] = session_status_template(max_attempts)
    for session in index.get("sessions", []):
        if session.get("session") == session_name:
            session.update(fields)
            break
    save_json(index_path, index)


def phase_prompt(root: Path, task_dir: Path, role_name: str, request: str, artifact: str, attempt: int, max_attempts: int) -> str:
    task_index = (task_dir / "index.json").read_text()
    extra = ""
    if role_name == "phase-plan":
        extra = f"""
## Task Creation Contract

{(root / ".agent-harness" / "prompts" / "task-create.md").read_text()}
"""
    return f"""You are running as an isolated phaseloop phase subagent.

{role_prompt(root, role_name)}

Headless mode:
- If AGENT_HEADLESS=1, do not ask questions.
- Write the required artifact to `{task_dir.relative_to(root) / artifact}`.
- Read previous artifacts from `{task_dir.relative_to(root)}/artifacts/`.
- Preserve the task directory and update `{task_dir.relative_to(root)}/index.json` when your phase requires it.

Attempt:
- This is attempt {attempt} of {max_attempts}.

## Original User Request

{request}

## Task Index

```json
{task_index}
```

## Previous Artifacts

{read_existing_artifacts(task_dir)}

## Project Docs

{docs_context(root)}
{extra}
"""


def analysis_prompt(root: Path, task_dir: Path, request: str, attempt: int, max_attempts: int) -> str:
    task_index = (task_dir / "index.json").read_text()
    task_contract = (root / ".agent-harness" / "prompts" / "task-create.md").read_text()
    return f"""You are running the phaseloop analysis session.

Clarify has already run in the main conversation. This headless session owns
the remaining analysis phases:

1. context gather
2. plan

Do not implement code. The goal is to produce durable artifacts and executable
phase files so a later build session can work from file state instead of this
conversation's memory.

## Context Gather Role

{role_prompt(root, "phase-context")}

## Plan Role

{role_prompt(root, "phase-plan")}

## Task Creation Contract

{task_contract}

## Headless Mode

- If AGENT_HEADLESS=1, do not ask questions.
- Use the existing clarify artifact as the request contract.
- If the clarify artifact is still insufficient, record assumptions and
  deferred scope instead of stopping for clarification.
- Write all required files before returning.
- Preserve workflow and session metadata already present in `{task_dir.relative_to(root)}/index.json`.

Attempt:
- This is analysis attempt {attempt} of {max_attempts}.

## Required Files

- `{task_dir.relative_to(root)}/artifacts/02-context.md`
- `{task_dir.relative_to(root)}/artifacts/03-plan.md`
- `{task_dir.relative_to(root)}/index.json`
- `{task_dir.relative_to(root)}/phase<N>.md` files for the build session

## Main-Session Clarify Artifact

{read_artifact_if_exists(task_dir, "artifacts/01-clarify.md") or "Missing clarify artifact."}

## Original User Request

{request}

## Task Index

```json
{task_index}
```

## Project Docs

{docs_context(root)}
"""


def missing_analysis_artifacts(task_dir: Path) -> list[str]:
    missing = []
    for _, _, artifact in ANALYSIS_PHASES:
        if not (task_dir / artifact).exists():
            missing.append(artifact)
    index = load_json(task_dir / "index.json")
    if not index.get("phases"):
        missing.append("phase<N>.md")
    return missing


def resolve_input_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return root / path


def seed_clarify_artifact(root: Path, task_dir: Path, clarify_file: Path) -> int:
    if not clarify_file.exists():
        raise FileNotFoundError(clarify_file)
    content = clarify_file.read_text().strip()
    if not content:
        raise ValueError(f"clarify file is empty: {clarify_file}")

    artifact = task_dir / CLARIFY_PHASE[2]
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(content + "\n")

    completed_at = now_iso()
    set_session_status(
        task_dir,
        "clarify",
        status="completed",
        attempts=1,
        max_attempts=1,
        completed_at=completed_at,
        source="main_session",
    )
    set_workflow_status(
        task_dir,
        "clarify",
        status="completed",
        attempts=1,
        max_attempts=1,
        completed_at=completed_at,
        source="main_session",
    )

    index_path = task_dir / "index.json"
    index = load_json(index_path)
    index["clarify"] = {
        "artifact": CLARIFY_PHASE[2],
        "source": "main_session",
        "source_file": str(clarify_file),
        "completed_at": completed_at,
    }
    save_json(index_path, index)
    log(f"phase=clarify completed source=main_session artifact={artifact.relative_to(root)}")
    return 0


def run_analysis_session(
    root: Path,
    task_dir: Path,
    provider: Any,
    request: str,
    max_attempts: int,
    timeout_sec: int,
) -> int:
    config = load_config(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    sandbox_mode = str(execution.get("sandbox_mode", "workspace-write"))
    approval_policy = str(execution.get("approval_policy", "never"))
    prompt_handoff = str(execution.get("prompt_handoff", "stdin"))

    for attempt in range(1, max_attempts + 1):
        log(f"session=analysis attempt={attempt}/{max_attempts} timeout={timeout_sec}s phases=context,plan")
        set_session_status(task_dir, "analysis", status="running", attempts=attempt)
        for phase_name, _, _ in ANALYSIS_PHASES:
            set_workflow_status(task_dir, phase_name, status="running", attempts=attempt)

        result = provider.run_prompt(
            analysis_prompt(root, task_dir, request, attempt, max_attempts),
            cwd=str(root),
            timeout_sec=timeout_sec,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            prompt_handoff=prompt_handoff,
            capture_json=True,
        )
        save_json(
            task_dir / f"analysis-output-attempt{attempt}.json",
            {
                "session": "analysis",
                "attempt": attempt,
                "provider": provider.name,
                **result,
            },
        )

        missing = missing_analysis_artifacts(task_dir)
        if not missing:
            completed_at = now_iso()
            set_session_status(task_dir, "analysis", status="completed", completed_at=completed_at)
            for phase_name, _, _ in ANALYSIS_PHASES:
                set_workflow_status(task_dir, phase_name, status="completed", completed_at=completed_at)
            log("session=analysis completed")
            return 0

        if attempt < max_attempts:
            log(f"session=analysis missing={','.join(missing)}; retrying")
            set_session_status(task_dir, "analysis", status="pending", last_failure_at=now_iso())
            for phase_name, _, _ in ANALYSIS_PHASES:
                set_workflow_status(task_dir, phase_name, status="pending", last_failure_at=now_iso())
            continue

        error = f"analysis did not create required files: {', '.join(missing)}"
        failed_at = now_iso()
        set_session_status(task_dir, "analysis", status="error", failed_at=failed_at, error_message=error)
        for phase_name, _, _ in ANALYSIS_PHASES:
            set_workflow_status(task_dir, phase_name, status="error", failed_at=failed_at, error_message=error)
        log("session=analysis failed")
        return 1

    return 1


def run_artifact_phase(
    root: Path,
    task_dir: Path,
    provider: Any,
    request: str,
    phase_name: str,
    role_name: str,
    artifact: str,
    max_attempts: int,
    timeout_sec: int,
    session_name: str | None = None,
) -> int:
    config = load_config(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    sandbox_mode = str(execution.get("sandbox_mode", "workspace-write"))
    approval_policy = str(execution.get("approval_policy", "never"))
    prompt_handoff = str(execution.get("prompt_handoff", "stdin"))

    for attempt in range(1, max_attempts + 1):
        log(f"phase={phase_name} attempt={attempt}/{max_attempts} timeout={timeout_sec}s artifact={task_dir / artifact}")
        if session_name:
            set_session_status(task_dir, session_name, status="running", attempts=attempt, max_attempts=max_attempts)
        set_workflow_status(task_dir, phase_name, status="running", attempts=attempt)
        result = provider.run_prompt(
            phase_prompt(root, task_dir, role_name, request, artifact, attempt, max_attempts),
            cwd=str(root),
            timeout_sec=timeout_sec,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            prompt_handoff=prompt_handoff,
            capture_json=True,
        )
        save_json(
            task_dir / f"{phase_name}-output-attempt{attempt}.json",
            {
                "phase": phase_name,
                "attempt": attempt,
                "provider": provider.name,
                **result,
            },
        )
        if (task_dir / artifact).exists():
            if phase_name == "evaluate":
                index = load_json(task_dir / "index.json")
                evaluation = index.get("evaluation", {})
                status = evaluation.get("status") if isinstance(evaluation, dict) else None
                if status not in ("pass", "warn") and attempt < max_attempts:
                    continue
                if status not in ("pass", "warn"):
                    set_workflow_status(task_dir, phase_name, status="error", failed_at=now_iso())
                    if session_name:
                        set_session_status(task_dir, session_name, status="error", failed_at=now_iso())
                    return 1
            set_workflow_status(task_dir, phase_name, status="completed", completed_at=now_iso())
            if session_name:
                set_session_status(task_dir, session_name, status="completed", completed_at=now_iso())
            log(f"phase={phase_name} completed")
            return 0
        if attempt < max_attempts:
            log(f"phase={phase_name} missing artifact; retrying")
            set_workflow_status(task_dir, phase_name, status="pending", last_failure_at=now_iso())
            continue

    set_workflow_status(
        task_dir,
        phase_name,
        status="error",
        failed_at=now_iso(),
        error_message=f"{artifact} was not created within max_attempts",
    )
    if session_name:
        set_session_status(
            task_dir,
            session_name,
            status="error",
            failed_at=now_iso(),
            error_message=f"{artifact} was not created within max_attempts",
        )
    log(f"phase={phase_name} failed")
    return 1


def run_generate(
    root: Path,
    task_dir: Path,
    provider_name: str | None,
    max_attempts: int,
    timeout_sec: int,
    commit_mode: str,
) -> int:
    artifact = task_dir / "artifacts" / "04-generate.md"
    if not artifact.exists():
        artifact.write_text("# Phase 4: Generate\n\n")
    set_session_status(task_dir, "build", status="running", attempts=1, max_attempts=max_attempts)
    set_workflow_status(task_dir, "generate", status="running", attempts=1, max_attempts=max_attempts)
    cmd = [
        sys.executable,
        str(root / "scripts" / "run-phases.py"),
        task_dir.name,
        "--max-attempts",
        str(max_attempts),
        "--skip-evaluation",
        "--session-timeout-sec",
        str(timeout_sec),
    ]
    if provider_name:
        cmd.extend(["--provider", provider_name])
    if commit_mode == "phase":
        cmd.extend(["--commit-mode", "phase"])
    log(f"phase=generate command={' '.join(cmd)}")
    index = load_json(task_dir / "index.json")
    phase_count = len(index.get("phases", [])) if isinstance(index.get("phases"), list) else 1
    process_timeout = max(60, timeout_sec * max_attempts * max(1, phase_count) + 60)
    process = subprocess.Popen(
        cmd,
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    stdout_parts: list[str] = []
    start = time.monotonic()
    assert process.stdout is not None
    while True:
        if time.monotonic() - start > process_timeout:
            process.kill()
            process.wait()
            output = {
                "exit_code": 124,
                "stdout": "".join(stdout_parts),
                "stderr": f"\nTimed out after {process_timeout}s",
            }
            save_json(task_dir / "generate-output.json", output)
            set_session_status(task_dir, "build", status="error", failed_at=now_iso(), error_message="run-phases timed out")
            set_workflow_status(task_dir, "generate", status="error", failed_at=now_iso(), error_message="run-phases timed out")
            log("phase=generate failed timeout")
            return 124

        ready, _, _ = select.select([process.stdout], [], [], 0.2)
        if ready:
            line = process.stdout.readline()
            if line:
                stdout_parts.append(line)
                print(line, end="", flush=True)

        if process.poll() is not None:
            remainder = process.stdout.read()
            if remainder:
                stdout_parts.append(remainder)
                print(remainder, end="", flush=True)
            break

    return_code = process.returncode if process.returncode is not None else process.wait()
    output = {
        "exit_code": return_code,
        "stdout": "".join(stdout_parts),
        "stderr": "",
    }
    if return_code == 124:
        output = {
            "exit_code": 124,
            "stdout": "".join(stdout_parts),
            "stderr": "\nrun-phases exited with timeout status 124",
        }
        save_json(task_dir / "generate-output.json", output)
        set_session_status(task_dir, "build", status="error", failed_at=now_iso(), error_message="run-phases timed out")
        set_workflow_status(task_dir, "generate", status="error", failed_at=now_iso(), error_message="run-phases timed out")
        log("phase=generate failed timeout")
        return 124
    save_json(
        task_dir / "generate-output.json",
        output,
    )
    if return_code == 0:
        set_session_status(task_dir, "build", status="completed", completed_at=now_iso())
        set_workflow_status(task_dir, "generate", status="completed", completed_at=now_iso())
        log("phase=generate completed")
        return 0
    set_session_status(task_dir, "build", status="error", failed_at=now_iso(), error_message="run-phases failed")
    set_workflow_status(task_dir, "generate", status="error", failed_at=now_iso(), error_message="run-phases failed")
    log("phase=generate failed")
    return return_code


def update_top_status(root: Path, task_dir: Path, status: str) -> None:
    top_path = root / "tasks" / "index.json"
    top = load_json(top_path, {"tasks": []})
    for item in top.get("tasks", []):
        if item.get("dir") == task_dir.name:
            item["status"] = status
            if status == "completed":
                item["completed_at"] = now_iso()
            elif status == "error":
                item["failed_at"] = now_iso()
            break
    save_json(top_path, top)


def run_workflow(
    request: str,
    provider_name: str | None,
    task_name: str | None,
    max_attempts: int,
    session_timeout_sec: int,
    commit_mode: str = "none",
    commit_message: str | None = None,
    clarify_file: Path | None = None,
) -> int:
    root = find_project_root()
    if clarify_file is None:
        log("phase=clarify failed: main-session clarify artifact is required; pass --clarify-file")
        return 2
    if not clarify_file.exists():
        log(f"phase=clarify failed: clarify file does not exist: {clarify_file}")
        return 2
    if not clarify_file.read_text().strip():
        log(f"phase=clarify failed: clarify file is empty: {clarify_file}")
        return 2

    config = load_config(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    session_strategy = str(execution.get("session_strategy", "balanced"))
    if session_strategy != "balanced":
        raise RuntimeError(f"Unsupported session_strategy: {session_strategy}")
    provider = load_provider(provider_name, root)
    task_dir = create_task(root, request, task_name or request.splitlines()[0][:60], max_attempts, session_strategy)
    log(f"created task=tasks/{task_dir.name} provider={provider.name} max_attempts={max_attempts} strategy={session_strategy}")

    seed_clarify_artifact(root, task_dir, clarify_file)

    code = run_analysis_session(root, task_dir, provider, request, max_attempts, session_timeout_sec)
    if code != 0:
        update_top_status(root, task_dir, "error")
        return code

    code = run_generate(root, task_dir, provider_name, max_attempts, session_timeout_sec, commit_mode)
    if code != 0:
        update_top_status(root, task_dir, "error")
        return code

    phase_name, role_name, artifact = ARTIFACT_AGENT_PHASES[3]
    code = run_artifact_phase(
        root,
        task_dir,
        provider,
        request,
        phase_name,
        role_name,
        artifact,
        max_attempts,
        session_timeout_sec,
        session_name="evaluate",
    )
    if code != 0:
        update_top_status(root, task_dir, "error")
        return code

    index = load_json(task_dir / "index.json")
    index["status"] = "completed"
    index["completed_at"] = now_iso()
    save_json(task_dir / "index.json", index)
    update_top_status(root, task_dir, "completed")
    log(f"workflow completed: tasks/{task_dir.name}")

    if commit_mode == "final":
        cmd = [sys.executable, str(root / "scripts" / "commit-result.py"), task_dir.name]
        if commit_message:
            cmd.extend(["--message", commit_message])
        log(f"commit-mode=final command={' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(root), text=True)
        return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a five-phase artifact workflow using main-session clarify plus balanced headless sessions."
    )
    parser.add_argument("request", nargs="*", help="Work request to execute")
    parser.add_argument("--request-file", default=None, help="Read the work request from a file")
    parser.add_argument("--provider", default=None, help="Provider name override")
    parser.add_argument("--task-name", default=None, help="Task name override")
    parser.add_argument("--max-attempts", type=int, default=None, help="Retry attempts for context/plan analysis, build phases, and evaluate")
    parser.add_argument("--session-timeout-sec", type=int, default=None, help="Timeout for each headless agent session or build phase call")
    parser.add_argument("--clarify-file", default=None, help="Path to the main-session clarify artifact markdown file")
    parser.add_argument("--phase-timeout-sec", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--commit-mode", choices=["none", "final", "phase"], default=None, help="Commit mode: none, final, or phase")
    parser.add_argument("--commit-on-success", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--commit-message", default=None, help="Commit message to use with --commit-mode final")
    args = parser.parse_args()

    root = find_project_root()
    config = load_config(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    max_attempts = args.max_attempts or int(execution.get("workflow_max_attempts", 2))
    commit_mode = args.commit_mode or str(execution.get("commit_mode", "none"))
    if args.commit_on_success:
        if args.commit_mode and args.commit_mode != "final":
            parser.error("--commit-on-success is only compatible with --commit-mode final")
        commit_mode = "final"
    if commit_message := args.commit_message:
        if commit_mode != "final":
            parser.error("--commit-message requires --commit-mode final")
    if commit_mode not in ("none", "final", "phase"):
        parser.error("--commit-mode must be one of: none, final, phase")
    session_timeout_sec = (
        args.session_timeout_sec
        or args.phase_timeout_sec
        or int(execution.get("session_timeout_sec", execution.get("phase_timeout_sec", 1800)))
    )

    if args.request_file:
        request = Path(args.request_file).read_text()
    else:
        request = " ".join(args.request).strip()
    if not request:
        parser.error("request text or --request-file is required")
    if not args.clarify_file:
        parser.error("--clarify-file is required because clarify runs in the main session before headless workflow")
    clarify_file = resolve_input_path(root, args.clarify_file) if args.clarify_file else None
    if clarify_file and not clarify_file.exists():
        parser.error(f"--clarify-file does not exist: {clarify_file}")
    if clarify_file and not clarify_file.read_text().strip():
        parser.error(f"--clarify-file is empty: {clarify_file}")
    return run_workflow(
        request,
        args.provider,
        args.task_name,
        max(1, max_attempts),
        max(1, session_timeout_sec),
        commit_mode,
        commit_message,
        clarify_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
