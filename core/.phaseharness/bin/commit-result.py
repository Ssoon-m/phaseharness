#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log(message: str) -> None:
    print(f"[phaseharness] {message}", flush=True)


def fail(message: str, code: int = 1) -> int:
    print(f"[phaseharness] error: {message}", file=sys.stderr, flush=True)
    return code


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True)


def git_head(root: Path) -> str:
    result = git(root, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def status_entries(root: Path) -> list[dict[str, str]]:
    result = git(root, "status", "--porcelain=v1", "-z")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    chunks = result.stdout.split("\0")
    entries: list[dict[str, str]] = []
    index = 0
    while index < len(chunks):
        raw = chunks[index]
        index += 1
        if not raw or len(raw) < 4:
            continue
        code = raw[:2]
        entry = {"code": code, "path": raw[3:]}
        if "R" in code or "C" in code:
            if index < len(chunks) and chunks[index]:
                entry["original_path"] = chunks[index]
                index += 1
        entries.append(entry)
    return entries


def paths_from_entries(entries: list[dict[str, str]]) -> set[str]:
    paths: set[str] = set()
    for entry in entries:
        paths.add(entry["path"])
        if "original_path" in entry:
            paths.add(entry["original_path"])
    return paths


def is_harness_managed_path(path: str) -> bool:
    normalized = path.rstrip("/")
    if normalized == ".phaseharness" or normalized.startswith(".phaseharness/"):
        return True
    if normalized in {".claude", ".agents", ".codex"}:
        return True
    if normalized in {".claude/settings.json", ".codex/config.toml", ".codex/hooks.json"}:
        return True
    if normalized == ".claude/skills/phaseharness" or normalized.startswith(".claude/skills/phaseharness/"):
        return True
    if normalized == ".claude/skills/commit" or normalized.startswith(".claude/skills/commit/"):
        return True
    if normalized == ".agents/skills/phaseharness" or normalized.startswith(".agents/skills/phaseharness/"):
        return True
    if normalized == ".agents/skills/commit" or normalized.startswith(".agents/skills/commit/"):
        return True
    if normalized.startswith(".claude/agents/phaseharness-"):
        return True
    if normalized.startswith(".codex/agents/phaseharness-"):
        return True
    return False


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


def infer_commit_message(state: dict[str, Any]) -> str:
    request = str(state.get("request") or "complete requested work")
    return f"{infer_commit_type(request)}: {clean_summary(request)}"


def latest_completed_run(root: Path) -> Path:
    index = load_json(root / ".phaseharness" / "state" / "index.json", {"runs": []})
    completed = [item for item in index.get("runs", []) if isinstance(item, dict) and item.get("status") == "completed"]
    if not completed:
        raise RuntimeError("no completed phaseharness run found")
    completed.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return root / ".phaseharness" / "runs" / str(completed[0]["run_id"])


def resolve_run_dir(root: Path, run_id: str | None) -> Path:
    if not run_id:
        return latest_completed_run(root)
    direct = root / ".phaseharness" / "runs" / run_id
    if direct.exists():
        return direct
    raise RuntimeError(f"run not found: {run_id}")


def update_index(root: Path, run_id: str, status: str) -> None:
    path = root / ".phaseharness" / "state" / "index.json"
    index = load_json(path, {"schema_version": 1, "runs": []})
    for item in index.get("runs", []):
        if isinstance(item, dict) and item.get("run_id") == run_id:
            item["status"] = status
            item["updated_at"] = now_iso()
            break
    save_json(path, index)


def validate_run_for_commit(run_dir: Path, mode: str, implementation_phase: str | None) -> dict[str, Any]:
    state = load_json(run_dir / "state.json")
    if mode == "completed":
        phases = state.get("phases", {}) if isinstance(state.get("phases"), dict) else {}
        evaluate = phases.get("evaluate", {}) if isinstance(phases.get("evaluate"), dict) else {}
        if state.get("status") != "completed" and evaluate.get("status") != "completed":
            raise RuntimeError(f"run is not completed: {run_dir.name}")
        evaluation = state.get("evaluation", {})
        evaluation_status = evaluation.get("status") if isinstance(evaluation, dict) else None
        if evaluation_status not in ("pass", "warn"):
            raise RuntimeError(f"run evaluation is not pass/warn: {evaluation_status or 'missing'}")
        return state
    if mode == "implementation-phase":
        if not implementation_phase:
            raise RuntimeError("--implementation-phase is required with --mode implementation-phase")
        generate = state.get("generate", {}) if isinstance(state.get("generate"), dict) else {}
        statuses = generate.get("phase_status", {}) if isinstance(generate.get("phase_status"), dict) else {}
        phase_status = statuses.get(implementation_phase)
        if phase_status != "completed":
            raise RuntimeError(f"implementation phase is not completed: {implementation_phase}")
        return state
    raise RuntimeError(f"unsupported commit mode: {mode}")


def stage_paths(root: Path, paths: list[str]) -> None:
    for start in range(0, len(paths), 100):
        chunk = paths[start : start + 100]
        result = git(root, "add", "--", *chunk)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def commit_result(
    root: Path,
    run_dir: Path,
    message: str | None,
    dry_run: bool,
    include_harness_state: bool,
    allow_head_move: bool,
    mode: str,
    implementation_phase: str | None,
) -> int:
    state = validate_run_for_commit(run_dir, mode, implementation_phase)
    baseline = state.get("git_baseline", {})
    baseline_head = str(baseline.get("head") or "") if isinstance(baseline, dict) else ""
    baseline_dirty_paths = set(baseline.get("dirty_paths", [])) if isinstance(baseline, dict) else set()
    product_baseline_dirty_paths = {path for path in baseline_dirty_paths if not is_harness_managed_path(path)}
    current_head = git_head(root)
    if baseline_head and current_head != baseline_head and not allow_head_move:
        return fail("git HEAD changed since this run started; commit manually or pass --allow-head-move", 2)

    cached = git(root, "diff", "--cached", "--quiet")
    if cached.returncode != 0:
        return fail("git index already has staged changes; commit manually", 2)

    current_paths = paths_from_entries(status_entries(root))
    blocked = sorted(path for path in current_paths & product_baseline_dirty_paths if not is_harness_managed_path(path))
    if blocked:
        log("baseline dirty paths still changed:")
        for path in blocked:
            print(f"  {path}")
        return fail("refusing to auto-commit because the worktree was dirty before phaseharness started", 2)

    changed_paths = current_paths - product_baseline_dirty_paths
    excluded = sorted(path for path in changed_paths if is_harness_managed_path(path))
    stageable = sorted(path for path in changed_paths if include_harness_state or not is_harness_managed_path(path))
    if not stageable:
        log("no product changes to commit")
        if excluded:
            log("excluded phaseharness managed paths:")
            for path in excluded:
                print(f"  {path}")
        return 0

    commit_message = message or infer_commit_message(state)
    log(f"commit message: {commit_message}")
    log("stageable paths:")
    for path in stageable:
        print(f"  {path}")
    if dry_run:
        return 0

    stage_paths(root, stageable)
    result = git(root, "commit", "-m", commit_message)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def record_commit_state(
    root: Path,
    run_dir: Path,
    key: str,
    mode: str,
    implementation_phase: str | None,
    exit_code: int,
) -> None:
    state_path = run_dir / "state.json"
    state = load_json(state_path)
    commits = state.setdefault("commits", {})
    record: dict[str, Any] = {
        "mode": mode,
        "status": "completed" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "head_after": git_head(root),
        "updated_at": now_iso(),
    }
    if implementation_phase:
        record["implementation_phase"] = implementation_phase
    commits[key] = record
    if exit_code != 0:
        state["status"] = "waiting_user"
        state["needs_user"] = True
        update_index(root, str(state.get("run_id")), "waiting_user")
    save_json(state_path, state)


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit a completed phaseharness run result.")
    parser.add_argument("run_id", nargs="?", help="Run id under .phaseharness/runs/. Defaults to latest completed run.")
    parser.add_argument("--message", default=None, help="Commit message override")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-harness-state", action="store_true", help="Include .phaseharness runtime state in the commit")
    parser.add_argument("--allow-head-move", action="store_true", help="Allow commit even if HEAD changed after the run started")
    parser.add_argument("--mode", choices=["completed", "implementation-phase"], default="completed")
    parser.add_argument("--implementation-phase", default=None, help="Implementation phase id for --mode implementation-phase")
    parser.add_argument("--record-state-key", default=None, help="Record this commit attempt under state.commits[KEY]")
    args = parser.parse_args()

    root = find_project_root()
    run_dir: Path | None = None
    exit_code = 1
    try:
        run_dir = resolve_run_dir(root, args.run_id)
        exit_code = commit_result(
            root,
            run_dir,
            args.message,
            args.dry_run,
            args.include_harness_state,
            args.allow_head_move,
            args.mode,
            args.implementation_phase,
        )
        return exit_code
    except Exception as exc:
        exit_code = fail(str(exc))
        return exit_code
    finally:
        if args.record_state_key and run_dir is not None and not args.dry_run:
            try:
                record_commit_state(root, run_dir, args.record_state_key, args.mode, args.implementation_phase, exit_code)
            except Exception as exc:
                print(f"[phaseharness] error: failed to record commit state: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
