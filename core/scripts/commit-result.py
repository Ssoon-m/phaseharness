#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from _utils import find_project_root, git, git_head, load_json, now_iso, save_json


def log(message: str) -> None:
    print(f"[phaseloop] {message}", flush=True)


def fail(message: str, code: int = 1) -> int:
    print(f"[phaseloop] error: {message}", file=sys.stderr, flush=True)
    return code


def run_git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = git(*args, root=root)
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def git_status_entries(root: Path) -> list[dict[str, str]]:
    result = run_git(root, "status", "--porcelain=v1", "-z", check=True)
    chunks = result.stdout.split("\0")
    entries: list[dict[str, str]] = []
    i = 0
    while i < len(chunks):
        raw = chunks[i]
        i += 1
        if not raw:
            continue
        if len(raw) < 4:
            continue
        code = raw[:2]
        path = raw[3:]
        entry = {"code": code, "path": path}
        if "R" in code or "C" in code:
            if i < len(chunks) and chunks[i]:
                entry["original_path"] = chunks[i]
                i += 1
        entries.append(entry)
    return entries


def status_paths(entries: list[dict[str, str]]) -> set[str]:
    paths: set[str] = set()
    for entry in entries:
        path = entry.get("path")
        if path:
            paths.add(path)
        original = entry.get("original_path")
        if original:
            paths.add(original)
    return paths


def latest_completed_task(root: Path) -> Path:
    top = load_json(root / "tasks" / "index.json", {"tasks": []})
    tasks = top.get("tasks", [])
    if not isinstance(tasks, list):
        raise RuntimeError("tasks/index.json does not contain a task list")
    completed = [item for item in tasks if isinstance(item, dict) and item.get("status") == "completed"]
    if not completed:
        raise RuntimeError("no completed phaseloop task found")
    completed.sort(key=lambda item: int(item.get("id", 0)), reverse=True)
    directory = str(completed[0].get("dir", ""))
    if not directory:
        raise RuntimeError("latest completed task has no dir")
    return root / "tasks" / directory


def resolve_task_dir(root: Path, task_arg: str | None) -> Path:
    if not task_arg:
        return latest_completed_task(root)
    direct = root / "tasks" / task_arg
    if direct.exists():
        return direct
    top = load_json(root / "tasks" / "index.json", {"tasks": []})
    for item in top.get("tasks", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("id")) == task_arg or str(item.get("name")) == task_arg:
            directory = str(item.get("dir", ""))
            if directory:
                return root / "tasks" / directory
    raise RuntimeError(f"task not found: {task_arg}")


def clean_summary(value: str, limit: int = 64) -> str:
    summary = re.sub(r"\s+", " ", value).strip()
    if not summary:
        return "complete requested work"
    if len(summary) <= limit:
        return summary
    return summary[: limit - 3].rstrip() + "..."


def infer_commit_type(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("fix", "bug", "error")):
        return "fix"
    if "refactor" in lower:
        return "refactor"
    if any(token in lower for token in ("doc", "readme")):
        return "docs"
    if "test" in lower:
        return "test"
    if "chore" in lower:
        return "chore"
    return "feat"


def infer_commit_message(index: dict[str, Any]) -> str:
    task = str(index.get("task") or "").strip()
    prompt = str(index.get("prompt") or "").strip()
    source = task or prompt or "complete requested work"
    commit_type = infer_commit_type(source)
    return f"{commit_type}: {clean_summary(source)}"


def infer_phase_commit_message(index: dict[str, Any], phase_ref: str) -> str:
    task = clean_summary(str(index.get("task") or index.get("prompt") or "completed work"), 64)
    if phase_ref == "evaluate":
        return f"chore: validate {task}"
    phase = find_phase(index, phase_ref)
    phase_name = str(phase.get("name") or "").strip()
    if phase_name and phase_name.lower() not in ("implementation", "generate", "build"):
        return f"feat: {clean_summary(phase_name, 64)}"
    return f"feat: {task}"


def configured_commit_message(index: dict[str, Any], phase_ref: str | None) -> str | None:
    if phase_ref:
        if phase_ref == "evaluate":
            evaluation = index.get("evaluation", {})
            if isinstance(evaluation, dict):
                value = evaluation.get("commit_message")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            value = index.get("validation_commit_message")
            if isinstance(value, str) and value.strip():
                return value.strip()
            return None
        phase = find_phase(index, phase_ref)
        value = phase.get("commit_message")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
    value = index.get("commit_message")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def find_phase(index: dict[str, Any], phase_ref: str) -> dict[str, Any]:
    for phase in index.get("phases", []):
        if not isinstance(phase, dict):
            continue
        if str(phase.get("phase")) == phase_ref:
            return phase
    raise RuntimeError(f"phase not found in task index: {phase_ref}")


def update_commit_metadata(task_dir: Path, **fields: Any) -> None:
    index_path = task_dir / "index.json"
    index = load_json(index_path)
    metadata = index.get("commit")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(fields)
    index["commit"] = metadata
    save_json(index_path, index)


def is_harness_state_path(path: str) -> bool:
    return path == "tasks" or path == "tasks/" or path.startswith("tasks/")


def validate_completed_task(task_dir: Path) -> dict[str, Any]:
    index_path = task_dir / "index.json"
    if not index_path.exists():
        raise RuntimeError(f"missing task index: {index_path}")
    index = load_json(index_path)
    if index.get("status") != "completed":
        raise RuntimeError(f"task is not completed: {task_dir.name}")
    evaluation = index.get("evaluation", {})
    evaluation_status = evaluation.get("status") if isinstance(evaluation, dict) else None
    if evaluation_status not in ("pass", "warn"):
        raise RuntimeError(f"task evaluation is not pass/warn: {evaluation_status or 'missing'}")
    return index


def validate_phase_task(task_dir: Path, phase_ref: str) -> dict[str, Any]:
    index_path = task_dir / "index.json"
    if not index_path.exists():
        raise RuntimeError(f"missing task index: {index_path}")
    index = load_json(index_path)
    if phase_ref == "evaluate":
        if index.get("status") != "completed":
            raise RuntimeError(f"task is not completed: {task_dir.name}")
        evaluation = index.get("evaluation", {})
        evaluation_status = evaluation.get("status") if isinstance(evaluation, dict) else None
        if evaluation_status not in ("pass", "warn"):
            raise RuntimeError(f"task evaluation is not pass/warn: {evaluation_status or 'missing'}")
        return index
    phase = find_phase(index, phase_ref)
    if phase.get("status") != "completed":
        raise RuntimeError(f"phase {phase_ref} is not completed")
    return index


def stage_paths(root: Path, paths: list[str]) -> None:
    for start in range(0, len(paths), 100):
        chunk = paths[start : start + 100]
        run_git(root, "add", "-A", "--", *chunk, check=True)


def print_paths(label: str, paths: list[str]) -> None:
    if not paths:
        return
    log(label)
    for path in paths:
        print(f"  {path}")


def commit_task_result(
    root: Path,
    task_dir: Path,
    message: str | None,
    dry_run: bool,
    allow_baseline_dirty: bool,
    allow_head_move: bool,
    include_harness_state: bool,
    allow_empty: bool,
    phase_ref: str | None = None,
) -> int:
    index = validate_phase_task(task_dir, phase_ref) if phase_ref else validate_completed_task(task_dir)
    baseline = index.get("git_baseline", {})
    baseline_head = str(baseline.get("head") or "") if isinstance(baseline, dict) else ""
    baseline_dirty_paths = set(baseline.get("dirty_paths", [])) if isinstance(baseline, dict) else set()
    current_head = git_head(root)

    if baseline_head and current_head != baseline_head and not allow_head_move:
        return fail(
            "git HEAD changed since this task started; rerun manually or pass --allow-head-move",
            2,
        )

    current_entries = git_status_entries(root)
    current_paths = status_paths(current_entries)
    blocked_paths = sorted(current_paths & baseline_dirty_paths)
    changed_paths = current_paths - baseline_dirty_paths
    excluded_harness_paths = sorted(path for path in changed_paths if is_harness_state_path(path))
    stageable_paths = sorted(
        path
        for path in changed_paths
        if include_harness_state or not is_harness_state_path(path)
    )
    cached_check = run_git(root, "diff", "--cached", "--quiet")
    if cached_check.returncode != 0:
        return fail(
            "git index already has staged changes; commit manually so phaseloop does not include unrelated staged work",
            2,
        )

    if blocked_paths and not allow_baseline_dirty:
        print_paths("baseline dirty paths still changed:", blocked_paths)
        return fail(
            "refusing to auto-commit because the worktree was dirty before phaseloop started",
            2,
        )

    if not stageable_paths and not allow_empty:
        log(f"no stageable changes for tasks/{task_dir.name}")
        if excluded_harness_paths:
            print_paths("excluded phaseloop artifact paths:", excluded_harness_paths)
        return 0

    commit_message = (
        message
        or configured_commit_message(index, phase_ref)
        or (infer_phase_commit_message(index, phase_ref) if phase_ref else infer_commit_message(index))
    )
    print_paths("stageable paths:", stageable_paths)
    print_paths("excluded phaseloop artifact paths:", excluded_harness_paths)
    if blocked_paths:
        print_paths("excluded baseline dirty paths:", blocked_paths)
    log(f"commit message: {commit_message}")

    if dry_run:
        return 0

    if include_harness_state:
        update_commit_metadata(
            task_dir,
            status="completed",
            message=commit_message,
            requested_at=now_iso(),
            baseline_head=baseline_head,
            scope="phase" if phase_ref else "task",
            phase=phase_ref,
        )
        task_index_path = str((task_dir / "index.json").relative_to(root))
        if task_index_path not in baseline_dirty_paths and task_index_path not in stageable_paths:
            stageable_paths.append(task_index_path)
            stageable_paths.sort()

    if stageable_paths:
        stage_paths(root, stageable_paths)
    diff_check = run_git(root, "diff", "--cached", "--quiet")
    if diff_check.returncode == 0 and not allow_empty:
        return fail("nothing staged for commit", 1)

    commit_args = ["commit", "-m", commit_message]
    if allow_empty and diff_check.returncode == 0:
        commit_args.insert(1, "--allow-empty")
    result = run_git(root, *commit_args)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        update_commit_metadata(
            task_dir,
            status="error",
            message=commit_message,
            failed_at=now_iso(),
            error_message=result.stderr.strip() or result.stdout.strip(),
        )
        return result.returncode

    sha = git_head(root)
    log(f"committed {sha[:12]} for tasks/{task_dir.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit a completed phaseloop task result.")
    parser.add_argument("task_dir", nargs="?", help="Task directory name under tasks/. Defaults to latest completed task.")
    parser.add_argument("--message", default=None, help="Commit message override")
    parser.add_argument("--phase", default=None, help="Commit a completed implementation phase number, or 'evaluate'")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be staged and committed")
    parser.add_argument("--include-harness-state", action="store_true", help="Include tasks/ phaseloop artifacts in the commit")
    parser.add_argument("--allow-empty", action="store_true", help="Create an empty commit when only phaseloop artifacts changed")
    parser.add_argument(
        "--allow-baseline-dirty",
        action="store_true",
        help="Commit stageable task changes while leaving paths that were dirty before the workflow unstaged",
    )
    parser.add_argument(
        "--allow-head-move",
        action="store_true",
        help="Allow committing even if HEAD changed after the task started",
    )
    args = parser.parse_args()

    root = find_project_root()
    try:
        task_dir = resolve_task_dir(root, args.task_dir)
        return commit_task_result(
            root,
            task_dir,
            args.message,
            args.dry_run,
            args.allow_baseline_dirty,
            args.allow_head_move,
            args.include_harness_state,
            args.allow_empty,
            args.phase,
        )
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
