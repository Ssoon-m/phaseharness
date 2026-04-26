#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from _utils import find_project_root, git_head, load_config, load_json, load_provider, now_iso, save_json


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


def build_phase_prompt(root: Path, task_dir: Path, phase: dict[str, Any]) -> str:
    phase_num = phase["phase"]
    phase_file = task_dir / f"phase{phase_num}.md"
    if not phase_file.exists():
        raise FileNotFoundError(phase_file)
    phase_content = phase_file.read_text()
    task_index = (task_dir / "index.json").read_text()
    docs = []
    for rel in ("docs/mission.md", "docs/spec.md", "docs/testing.md", "docs/user-intervention.md"):
        path = root / rel
        if path.exists():
            docs.append(f"## {rel}\n\n{path.read_text()}")
    docs_text = "\n\n".join(docs) if docs else "No project docs found."
    return f"""You are executing one harness phase in an independent session.

Headless mode:
- If AGENT_HEADLESS=1, do not ask questions.
- Run the acceptance criteria commands yourself when possible.
- Update `{task_dir.relative_to(root)}/index.json` with the final phase status.
- Use `context_insufficient`, `validation_failed`, `sandbox_blocked`, or `runtime_error` in `error_message` when failing.

## Task Index

```json
{task_index}
```

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


def run_phases(task_dir_name: str, provider_name: str | None = None) -> int:
    root = find_project_root()
    config = load_config(root)
    provider = load_provider(provider_name, root)
    task_dir = root / "tasks" / task_dir_name
    index_path = task_dir / "index.json"
    if not index_path.exists():
        print(f"missing task index: {index_path}")
        return 1

    baseline = git_head(root)
    timeout = int(config.get("execution", {}).get("phase_timeout_sec", 1800))
    sandbox_mode = str(config.get("execution", {}).get("sandbox_mode", "workspace-write"))
    approval_policy = str(config.get("execution", {}).get("approval_policy", "never"))
    prompt_handoff = str(config.get("execution", {}).get("prompt_handoff", "stdin"))

    while True:
        index = load_json(index_path)
        phase = find_next_phase(index)
        if phase is None:
            index["completed_at"] = now_iso()
            save_json(index_path, index)
            update_top_index(root, task_dir_name, "completed")
            print(f"all phases completed: {task_dir_name}")
            return 0

        phase_num = int(phase["phase"])
        set_phase_field(index, phase_num, started_at=phase.get("started_at", now_iso()))
        save_json(index_path, index)

        prompt = build_phase_prompt(root, task_dir, phase)
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
            print(f"phase {phase_num} completed")
            continue

        if status != "error":
            failure = result["failure_category"] or "runtime_error"
            set_phase_field(
                fresh_index,
                phase_num,
                status="error",
                failed_at=now_iso(),
                error_message=f"{failure}: phase did not mark itself completed",
            )
            save_json(index_path, fresh_index)

        update_top_index(root, task_dir_name, "error")
        print(f"phase {phase_num} failed")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pending phases for a harness task.")
    parser.add_argument("task_dir", help="Task directory name under tasks/")
    parser.add_argument("--provider", default=None, help="Provider name override")
    args = parser.parse_args()
    return run_phases(args.task_dir, args.provider)


if __name__ == "__main__":
    raise SystemExit(main())
