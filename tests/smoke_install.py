#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import json
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


def write_existing_hooks(target: Path) -> None:
    (target / ".claude").mkdir(exist_ok=True)
    (target / ".codex").mkdir(exist_ok=True)
    (target / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo existing-claude-hook",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )
    (target / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "echo existing-codex-hook",
                                }
                            ],
                        }
                    ]
                }
            },
            indent=2,
        )
        + "\n"
    )


def assert_hook_merge(target: Path) -> None:
    claude = json.loads((target / ".claude" / "settings.json").read_text())
    codex = json.loads((target / ".codex" / "hooks.json").read_text())
    claude_text = json.dumps(claude)
    codex_text = json.dumps(codex)
    if "existing-claude-hook" not in claude_text:
        raise SystemExit("existing Claude hook was not preserved")
    if "existing-codex-hook" not in codex_text:
        raise SystemExit("existing Codex hook was not preserved")
    if claude_text.count("phaseloop-sync-bridges") != 2:
        raise SystemExit("Claude phaseloop hooks were not installed idempotently")
    if codex_text.count("phaseloop-sync-bridges") != 2:
        raise SystemExit("Codex phaseloop hooks were not installed idempotently")
    config = (target / ".codex" / "config.toml").read_text()
    if "codex_hooks = true" not in config:
        raise SystemExit("Codex hooks feature flag was not enabled")


def assert_inline_codex_merge(tmp: Path) -> None:
    target = tmp / "inline-codex"
    target.mkdir()
    copy_core(target)
    (target / ".codex").mkdir(exist_ok=True)
    (target / ".codex" / "config.toml").write_text(
        "[features]\ncodex_hooks = false\n\n"
        "[[hooks.PostToolUse]]\n"
        "matcher = \"Bash\"\n"
        "[[hooks.PostToolUse.hooks]]\n"
        "type = \"command\"\n"
        "command = \"echo existing-inline-codex-hook\"\n"
    )
    run(["python3", "scripts/install-hooks.py", "--runtime", "codex"], target)
    config = (target / ".codex" / "config.toml").read_text()
    if "existing-inline-codex-hook" not in config:
        raise SystemExit("existing inline Codex hook was not preserved")
    if "codex_hooks = true" not in config:
        raise SystemExit("inline Codex hooks feature flag was not enabled")
    if config.count("# BEGIN phaseloop managed hook") != 1:
        raise SystemExit("inline Codex phaseloop hook block was not installed once")
    if (target / ".codex" / "hooks.json").exists():
        raise SystemExit("inline-only Codex hook install should not create hooks.json")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="harness-smoke-") as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "target"
        target.mkdir()
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
        write_existing_hooks(target)
        assert_inline_codex_merge(tmp_path)

        run(["python3", "scripts/gen-bridges.py"], target)
        run(["python3", "scripts/install-hooks.py"], target)
        run(["python3", "scripts/install-hooks.py"], target)
        assert_hook_merge(target)
        run(["python3", "scripts/sync-bridges.py", "--force"], target)
        run(["sh", ".claude/hooks/phaseloop-sync-bridges.sh"], target)
        run(["sh", ".codex/hooks/phaseloop-sync-bridges.sh"], target)
        expected = [
            ".claude/skills",
            ".agents/skills",
            ".claude/hooks/phaseloop-sync-bridges.sh",
            ".codex/hooks/phaseloop-sync-bridges.sh",
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
        run(["python3", "scripts/install-hooks.py", "--help"], target)
        run(["python3", "scripts/sync-bridges.py", "--help"], target)
        run(["python3", "scripts/gen-docs-diff.py", "--help"], target)
        run(
            [
                "python3",
                "-m",
                "py_compile",
                "scripts/_utils.py",
                "scripts/gen-bridges.py",
                "scripts/gen-docs-diff.py",
                "scripts/install-hooks.py",
                "scripts/run-phases.py",
                "scripts/run-workflow.py",
                "scripts/sync-bridges.py",
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
