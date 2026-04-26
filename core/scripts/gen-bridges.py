#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from _utils import find_project_root, load_config, load_toml


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def multiline_toml(value: str) -> str:
    escaped = value.replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


def role_to_claude(role: dict[str, Any], prompt: str) -> str:
    name = str(role["name"])
    description = str(role.get("description", ""))
    tools_policy = str(role.get("tools_policy", "read-only"))
    tools = "Read, Grep, Glob, Bash" if tools_policy == "read-only" else "Read, Edit, Write, Grep, Glob, Bash"
    return f"""---
name: {name}
description: {description}
tools: {tools}
model: inherit
---

{prompt}
"""


def role_to_codex(role: dict[str, Any], prompt: str) -> str:
    name = str(role["name"]).replace("-", "_")
    description = str(role.get("description", ""))
    sandbox_mode = str(role.get("sandbox_mode", "read-only"))
    return "\n".join(
        [
            f"name = {toml_string(name)}",
            f"description = {toml_string(description)}",
            f"sandbox_mode = {toml_string(sandbox_mode)}",
            "developer_instructions = " + multiline_toml(prompt),
            "",
        ]
    )


def generate_agent_bridges(root: Path) -> list[Path]:
    roles_dir = root / ".agent-harness" / "roles"
    generated: list[Path] = []
    if not roles_dir.exists():
        return generated

    claude_agents = root / ".claude" / "agents"
    codex_agents = root / ".codex" / "agents"
    claude_agents.mkdir(parents=True, exist_ok=True)
    codex_agents.mkdir(parents=True, exist_ok=True)

    for role_dir in sorted(p for p in roles_dir.iterdir() if p.is_dir()):
        role_file = role_dir / "role.toml"
        prompt_file = role_dir / "prompt.md"
        if not role_file.exists() or not prompt_file.exists():
            continue
        role = load_toml(role_file)
        prompt = prompt_file.read_text()
        name = str(role.get("name", role_dir.name))

        claude_path = claude_agents / f"{name}.md"
        claude_path.write_text(role_to_claude({**role, "name": name}, prompt))
        generated.append(claude_path)

        codex_path = codex_agents / f"{name}.toml"
        codex_path.write_text(role_to_codex({**role, "name": name}, prompt))
        generated.append(codex_path)

    return generated


def link_or_copy_skills(root: Path, mode: str) -> list[Path]:
    source = root / ".agent-harness" / "skills"
    if not source.exists() or mode == "none":
        return []
    targets = [root / ".claude" / "skills", root / ".agents" / "skills"]
    generated: list[Path] = []
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            if target.is_symlink() and target.resolve() == source.resolve():
                generated.append(target)
                continue
            if mode == "copy" and target.is_dir() and not target.is_symlink():
                shutil.copytree(source, target, dirs_exist_ok=True)
                generated.append(target)
                continue
            print(f"skip existing skill bridge: {target}")
            continue
        if mode == "copy":
            shutil.copytree(source, target)
        else:
            target.symlink_to(Path("..") / ".agent-harness" / "skills", target_is_directory=True)
        generated.append(target)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate runtime bridge files.")
    parser.add_argument("--skills-mode", choices=["symlink", "copy", "none"], default=None)
    args = parser.parse_args()

    root = find_project_root()
    config = load_config(root)
    bridge_config = config.get("bridges", {}) if isinstance(config.get("bridges"), dict) else {}
    mode = args.skills_mode or str(bridge_config.get("skills_mode", "symlink"))

    generated = []
    generated.extend(link_or_copy_skills(root, mode))
    generated.extend(generate_agent_bridges(root))
    for path in generated:
        print(path.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
