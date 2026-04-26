#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from _utils import find_project_root


def generate(task_dir: Path, baseline: str, root: Path) -> Path:
    task_dir = task_dir if task_dir.is_absolute() else root / task_dir
    task_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "diff", baseline, "--", "docs/"],
        cwd=str(root),
        text=True,
        capture_output=True,
    )
    diff_text = result.stdout.strip()
    output = task_dir / "docs-diff.md"
    body = [
        f"# docs-diff: {task_dir.name}",
        "",
        f"Baseline: `{baseline}`",
        "",
    ]
    if diff_text:
        body.extend(["```diff", diff_text, "```", ""])
    else:
        body.extend(["No docs changes detected.", ""])
    output.write_text("\n".join(body))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docs diff for a harness task.")
    parser.add_argument("task_dir", help="Task directory path or name under tasks/")
    parser.add_argument("baseline", help="Baseline commit SHA")
    args = parser.parse_args()

    root = find_project_root()
    task_dir = Path(args.task_dir)
    if not task_dir.is_absolute() and not str(task_dir).startswith("tasks/"):
        task_dir = Path("tasks") / task_dir
    output = generate(task_dir, args.baseline, root)
    print(output.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
