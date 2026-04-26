#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)


def copy_core(target: Path) -> None:
    (target / ".agent-harness").mkdir()
    (target / "scripts").mkdir()
    (target / "docs").mkdir()
    (target / "tasks").mkdir()

    shutil.copytree(
        ROOT / "core" / ".agent-harness",
        target / ".agent-harness",
        dirs_exist_ok=True,
    )
    for script in (ROOT / "core" / "scripts").glob("*.py"):
        shutil.copy2(script, target / "scripts" / script.name)
    for doc in (ROOT / "core" / "templates" / "docs").glob("*.md"):
        shutil.copy2(doc, target / "docs" / doc.name)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="harness-smoke-") as tmp:
        target = Path(tmp)
        run(["git", "init", "--initial-branch=main"], target)
        run(
            [
                "git",
                "-c",
                "user.name=Harness Smoke",
                "-c",
                "user.email=smoke@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "test: initial fixture",
            ],
            target,
        )
        copy_core(target)

        run(["python3", "scripts/gen-bridges.py"], target)
        expected = [
            ".claude/skills",
            ".agents/skills",
            ".claude/agents/phase-clarify.md",
            ".codex/agents/phase-clarify.toml",
            ".claude/agents/phase-context.md",
            ".codex/agents/phase-context.toml",
            ".claude/agents/phase-plan.md",
            ".codex/agents/phase-plan.toml",
            ".claude/agents/phase-generate.md",
            ".codex/agents/phase-generate.toml",
            ".claude/agents/phase-evaluate.md",
            ".codex/agents/phase-evaluate.toml",
        ]
        for rel in expected:
            if not (target / rel).exists():
                raise SystemExit(f"missing generated bridge: {rel}")

        run(["python3", "scripts/run-workflow.py", "--help"], target)
        run(["python3", "scripts/run-phases.py", "--help"], target)
        run(["python3", "scripts/gen-docs-diff.py", "--help"], target)
        run(
            [
                "python3",
                "-m",
                "py_compile",
                "scripts/_utils.py",
                "scripts/gen-bridges.py",
                "scripts/gen-docs-diff.py",
                "scripts/run-phases.py",
                "scripts/run-workflow.py",
                ".agent-harness/providers/base.py",
                ".agent-harness/providers/claude.py",
                ".agent-harness/providers/codex.py",
                ".agent-harness/providers/registry.py",
            ],
            target,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
