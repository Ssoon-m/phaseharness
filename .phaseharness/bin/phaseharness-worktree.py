#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise RuntimeError("could not find git project root")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True)


def require_git_repo(root: Path) -> None:
    result = git(root, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise RuntimeError("phaseharness worktrees require a git worktree")
    head = git(root, "rev-parse", "--verify", "HEAD")
    if head.returncode != 0:
        raise RuntimeError("phaseharness worktrees require an initial commit")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "run"


def branch_exists(root: Path, branch: str) -> bool:
    result = git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    return result.returncode == 0


def default_worktree_path(root: Path, name: str) -> Path:
    return root.parent / f"{root.name}.worktrees" / name


def next_name(root: Path, request: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{slugify(request)}"
    candidate = base
    suffix = 2
    while branch_exists(root, f"phaseharness/{candidate}") or default_worktree_path(root, candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def resolve_base(root: Path, base: str) -> str:
    result = git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    if result.returncode != 0:
        raise RuntimeError(f"base ref is not a commit: {base}")
    return result.stdout.strip()


def create_worktree(root: Path, path: Path, branch: str, base: str) -> None:
    if path.exists():
        raise RuntimeError(f"worktree path already exists: {path}")
    if branch_exists(root, branch):
        raise RuntimeError(f"branch already exists: {branch}")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = git(root, "worktree", "add", "-b", branch, str(path), base)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git worktree add failed")


def command_create(args: argparse.Namespace) -> int:
    root = find_project_root()
    require_git_repo(root)
    run_id = args.name or next_name(root, args.request)
    branch = args.branch or f"phaseharness/{run_id}"
    path = Path(args.path).expanduser().resolve() if args.path else default_worktree_path(root, run_id)
    base = resolve_base(root, args.base)
    create_worktree(root, path, branch, base)
    output: dict[str, Any] = {
        "run_id": run_id,
        "branch": branch,
        "worktree_path": str(path),
        "base": base,
        "base_ref": args.base,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False) if args.json else str(path))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create phaseharness git worktrees for parallel runs.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a phaseharness worktree and branch")
    create.add_argument("--request", required=True)
    create.add_argument("--base", default="HEAD")
    create.add_argument("--name")
    create.add_argument("--branch")
    create.add_argument("--path")
    create.add_argument("--json", action="store_true")
    create.set_defaults(func=command_create)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
