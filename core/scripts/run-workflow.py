#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _utils import ensure_base_state, find_project_root, load_config, load_json, load_provider, now_iso, save_json


ARTIFACT_AGENT_PHASES = [
    ("clarify", "phase-clarify", "artifacts/01-clarify.md"),
    ("context", "phase-context", "artifacts/02-context.md"),
    ("plan", "phase-plan", "artifacts/03-plan.md"),
    ("evaluate", "phase-evaluate", "artifacts/05-evaluate.md"),
]

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


def create_task(root: Path, request: str, task_name: str, max_attempts: int) -> Path:
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


def run_artifact_phase(
    root: Path,
    task_dir: Path,
    provider: Any,
    request: str,
    phase_name: str,
    role_name: str,
    artifact: str,
    max_attempts: int,
) -> int:
    config = load_config(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    timeout = int(execution.get("phase_timeout_sec", 1800))
    sandbox_mode = str(execution.get("sandbox_mode", "workspace-write"))
    approval_policy = str(execution.get("approval_policy", "never"))
    prompt_handoff = str(execution.get("prompt_handoff", "stdin"))

    for attempt in range(1, max_attempts + 1):
        set_workflow_status(task_dir, phase_name, status="running", attempts=attempt)
        result = provider.run_prompt(
            phase_prompt(root, task_dir, role_name, request, artifact, attempt, max_attempts),
            cwd=str(root),
            timeout_sec=timeout,
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
                    return 1
            set_workflow_status(task_dir, phase_name, status="completed", completed_at=now_iso())
            return 0
        if attempt < max_attempts:
            set_workflow_status(task_dir, phase_name, status="pending", last_failure_at=now_iso())
            continue

    set_workflow_status(
        task_dir,
        phase_name,
        status="error",
        failed_at=now_iso(),
        error_message=f"{artifact} was not created within max_attempts",
    )
    return 1


def run_generate(root: Path, task_dir: Path, provider_name: str | None, max_attempts: int) -> int:
    artifact = task_dir / "artifacts" / "04-generate.md"
    if not artifact.exists():
        artifact.write_text("# Phase 4: Generate\n\n")
    set_workflow_status(task_dir, "generate", status="running", attempts=1, max_attempts=max_attempts)
    cmd = [
        sys.executable,
        str(root / "scripts" / "run-phases.py"),
        task_dir.name,
        "--max-attempts",
        str(max_attempts),
        "--skip-evaluation",
    ]
    if provider_name:
        cmd.extend(["--provider", provider_name])
    result = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
    save_json(
        task_dir / "generate-output.json",
        {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode == 0:
        set_workflow_status(task_dir, "generate", status="completed", completed_at=now_iso())
        return 0
    set_workflow_status(task_dir, "generate", status="error", failed_at=now_iso(), error_message="run-phases failed")
    return result.returncode


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


def run_workflow(request: str, provider_name: str | None, task_name: str | None, max_attempts: int) -> int:
    root = find_project_root()
    provider = load_provider(provider_name, root)
    task_dir = create_task(root, request, task_name or request.splitlines()[0][:60], max_attempts)
    print(f"created task: tasks/{task_dir.name}")

    for phase_name, role_name, artifact in ARTIFACT_AGENT_PHASES[:3]:
        code = run_artifact_phase(root, task_dir, provider, request, phase_name, role_name, artifact, max_attempts)
        if code != 0:
            update_top_status(root, task_dir, "error")
            return code

    code = run_generate(root, task_dir, provider_name, max_attempts)
    if code != 0:
        update_top_status(root, task_dir, "error")
        return code

    phase_name, role_name, artifact = ARTIFACT_AGENT_PHASES[3]
    code = run_artifact_phase(root, task_dir, provider, request, phase_name, role_name, artifact, max_attempts)
    if code != 0:
        update_top_status(root, task_dir, "error")
        return code

    index = load_json(task_dir / "index.json")
    index["status"] = "completed"
    index["completed_at"] = now_iso()
    save_json(task_dir / "index.json", index)
    update_top_status(root, task_dir, "completed")
    print(f"workflow completed: tasks/{task_dir.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a five-phase artifact workflow for an explicit request.")
    parser.add_argument("request", nargs="*", help="Work request to execute")
    parser.add_argument("--request-file", default=None, help="Read the work request from a file")
    parser.add_argument("--provider", default=None, help="Provider name override")
    parser.add_argument("--task-name", default=None, help="Task name override")
    parser.add_argument("--max-attempts", type=int, default=None, help="Retry attempts per workflow phase")
    args = parser.parse_args()

    root = find_project_root()
    config = load_config(root)
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    max_attempts = args.max_attempts or int(execution.get("workflow_max_attempts", 2))

    if args.request_file:
        request = Path(args.request_file).read_text()
    else:
        request = " ".join(args.request).strip()
    if not request:
        parser.error("request text or --request-file is required")
    return run_workflow(request, args.provider, args.task_name, max(1, max_attempts))


if __name__ == "__main__":
    raise SystemExit(main())
