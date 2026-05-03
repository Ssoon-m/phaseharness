#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
from pathlib import Path
from typing import Any


HOOK_MARKER = ".phaseharness"
SUBAGENTS = {
    "clarify": {
        "file": "clarify.md",
        "claude_name": "phaseharness-clarify",
        "codex_name": "phaseharness_clarify",
        "description": "Use proactively for the phaseharness clarify phase when an active phaseharness run needs an execution contract.",
    },
    "context-gather": {
        "file": "context-gather.md",
        "claude_name": "phaseharness-context-gather",
        "codex_name": "phaseharness_context_gather",
        "description": "Use proactively for the phaseharness context gather phase to inspect repository facts without implementing.",
    },
    "plan": {
        "file": "plan.md",
        "claude_name": "phaseharness-plan",
        "codex_name": "phaseharness_plan",
        "description": "Use proactively for the phaseharness plan phase to create implementation phase files and acceptance criteria.",
    },
    "generate": {
        "file": "generate.md",
        "claude_name": "phaseharness-generate",
        "codex_name": "phaseharness_generate",
        "description": "Use proactively for the phaseharness generate phase to implement exactly one queued implementation phase.",
    },
    "evaluate": {
        "file": "evaluate.md",
        "claude_name": "phaseharness-evaluate",
        "codex_name": "phaseharness_evaluate",
        "description": "Use proactively for the phaseharness evaluate phase to verify the run and queue follow-up phases on failure.",
    },
}

CLAUDE_AGENT_ALLOW_RULES = [f"Agent({item['claude_name']})" for item in SUBAGENTS.values()]


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return data


def load_harness_config(root: Path) -> dict[str, Any]:
    path = root / ".phaseharness" / "config.toml"
    if not path.exists():
        raise RuntimeError(f"missing phaseharness config: {path}")
    return parse_simple_toml(path.read_text(), path)


def parse_simple_toml_value(value: str, path: Path, line_number: int) -> Any:
    value = value.strip()
    if value in ("true", "false"):
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_simple_toml_value(part.strip(), path, line_number) for part in inner.split(",")]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    raise RuntimeError(f"unsupported TOML value in {path}:{line_number}: {value}")


def parse_simple_toml(text: str, path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current = data
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = data
            for part in line[1:-1].split("."):
                key = part.strip()
                if not key:
                    raise RuntimeError(f"empty TOML section in {path}:{line_number}")
                current = current.setdefault(key, {})
                if not isinstance(current, dict):
                    raise RuntimeError(f"TOML section conflicts with value in {path}:{line_number}: {key}")
            continue
        if "=" not in line:
            raise RuntimeError(f"unsupported TOML line in {path}:{line_number}: {raw}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeError(f"empty TOML key in {path}:{line_number}")
        current[key] = parse_simple_toml_value(value, path, line_number)
    return data


def nested_config(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, dict) else {}


def config_int(data: dict[str, Any], default: int, *keys: str) -> int:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return int(current) if current is not None else default


def config_str(data: dict[str, Any], default: str, *keys: str) -> str:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return str(current) if current is not None else default


def config_bool(data: dict[str, Any], default: bool, *keys: str) -> bool:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return bool(current) if current is not None else default


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def make_executable(path: Path) -> None:
    if path.exists():
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def toml_literal_multiline(value: str) -> str:
    return "'''\n" + value.replace("'''", "'''\"'\"'''") + "\n'''"


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return toml_string(str(value))


def yaml_frontmatter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def command_for(runtime: str) -> str:
    if runtime == "claude":
        return (
            "sh -c 'd=\"${CLAUDE_PROJECT_DIR:-$PWD}\"; "
            "while [ \"$d\" != \"/\" ]; do "
            "f=\"$d/.phaseharness/hooks/claude-stop.sh\"; "
            "if [ -x \"$f\" ]; then exec \"$f\"; fi; "
            "d=\"$(dirname \"$d\")\"; "
            "done; exit 0'"
        )
    if runtime == "codex":
        return (
            "sh -c 'root=\"$(git rev-parse --show-toplevel 2>/dev/null || pwd)\"; "
            "exec python3 \"$root/.phaseharness/bin/phaseharness-hook.py\" --runtime codex'"
        )
    raise ValueError(runtime)


def hook_entry(runtime: str, config: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "command",
        "command": command_for(runtime),
        "timeout": config_int(config, 30, "hooks", "timeout_sec"),
    }
    if runtime == "codex":
        entry["statusMessage"] = "Checking phaseharness state"
    return entry


def command_is_phaseharness(value: Any) -> bool:
    return isinstance(value, dict) and HOOK_MARKER in str(value.get("command", ""))


def merge_stop_hook(data: dict[str, Any], entry: dict[str, Any]) -> None:
    hooks_root = data.setdefault("hooks", {})
    if not isinstance(hooks_root, dict):
        raise RuntimeError("hooks must be an object")
    groups = hooks_root.setdefault("Stop", [])
    if not isinstance(groups, list):
        raise RuntimeError("hooks.Stop must be a list")

    target: dict[str, Any] | None = None
    for group in groups:
        if isinstance(group, dict) and str(group.get("matcher", "")) == "":
            target = group
            break
    if target is None:
        target = {"hooks": []}
        groups.append(target)

    entries = target.setdefault("hooks", [])
    if not isinstance(entries, list):
        raise RuntimeError("hooks.Stop[].hooks must be a list")
    entries[:] = [item for item in entries if not command_is_phaseharness(item)]
    entries.append(entry)


def ensure_claude_permissions(data: dict[str, Any], config: dict[str, Any]) -> None:
    permissions = data.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise RuntimeError("permissions must be an object")
    configured = nested_config(config, "permissions", "claude", "settings", "permissions")
    for key, value in configured.items():
        permissions[key] = value
    if "defaultMode" not in permissions:
        permissions["defaultMode"] = "bypassPermissions"
    phaseharness = nested_config(config, "permissions", "claude", "phaseharness")
    if config_bool(phaseharness, True, "allowManagedSubagents"):
        allow = permissions.setdefault("allow", [])
        if not isinstance(allow, list):
            raise RuntimeError("permissions.allow must be a list")
        for rule in CLAUDE_AGENT_ALLOW_RULES:
            if rule not in allow:
                allow.append(rule)


def install_claude_hooks(root: Path, config: dict[str, Any]) -> list[Path]:
    make_executable(root / ".phaseharness" / "hooks" / "claude-stop.sh")
    settings_path = root / ".claude" / "settings.json"
    data = load_json_object(settings_path)
    merge_stop_hook(data, hook_entry("claude", config))
    ensure_claude_permissions(data, config)
    write_json(settings_path, data)
    return [settings_path]


def ensure_codex_feature_flag(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text() if path.exists() else ""
    lines = text.splitlines()
    feature_header = re.compile(r"^\s*\[features\]\s*$")
    section_header = re.compile(r"^\s*\[[^\]]+\]\s*$")

    for index, line in enumerate(lines):
        if not feature_header.match(line):
            continue
        cursor = index + 1
        while cursor < len(lines) and not section_header.match(lines[cursor]):
            if re.match(r"^\s*codex_hooks\s*=", lines[cursor]):
                lines[cursor] = "codex_hooks = true"
                path.write_text("\n".join(lines).rstrip() + "\n")
                return
            cursor += 1
        lines.insert(index + 1, "codex_hooks = true")
        path.write_text("\n".join(lines).rstrip() + "\n")
        return

    prefix = "\n\n" if text.strip() else ""
    path.write_text(text.rstrip() + f"{prefix}[features]\ncodex_hooks = true\n")


def has_inline_codex_hooks(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text()
    return bool(re.search(r"(?m)^\s*\[hooks\]\s*$|^\s*\[\[hooks\.", text))


def remove_managed_toml_block(text: str) -> str:
    pattern = re.compile(
        r"\n?# BEGIN phaseharness managed hook\n.*?# END phaseharness managed hook\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text).rstrip() + "\n"


def remove_managed_permissions_block(text: str) -> str:
    pattern = re.compile(
        r"\n?# BEGIN phaseharness managed permissions\n.*?# END phaseharness managed permissions\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text).rstrip() + "\n"


def remove_root_toml_keys(text: str, keys: set[str]) -> str:
    lines = text.splitlines()
    output: list[str] = []
    in_root = True
    key_pattern = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=")
    section_pattern = re.compile(r"^\s*\[")
    for line in lines:
        if section_pattern.match(line):
            in_root = False
        if in_root:
            match = key_pattern.match(line)
            if match and match.group(1) in keys:
                continue
        output.append(line)
    return "\n".join(output).rstrip() + "\n"


def ensure_codex_permissions(config_path: Path, config: dict[str, Any]) -> None:
    text = config_path.read_text() if config_path.exists() else ""
    text = remove_managed_permissions_block(text)
    text = remove_root_toml_keys(
        text,
        {
            "approval_policy",
            "sandbox_mode",
            "sandbox_workspace_write.network_access",
            "sandbox_workspace_write.writable_roots",
        },
    )
    codex = nested_config(config, "permissions", "codex", "config")
    sandbox = nested_config(codex, "sandbox_workspace_write")
    lines = [
        "# BEGIN phaseharness managed permissions",
        f"approval_policy = {toml_value(codex.get('approval_policy', 'never'))}",
        f"sandbox_mode = {toml_value(codex.get('sandbox_mode', 'danger-full-access'))}",
    ]
    for key, value in sandbox.items():
        lines.append(f"sandbox_workspace_write.{key} = {toml_value(value)}")
    lines.append("# END phaseharness managed permissions")
    block = "\n".join(lines) + "\n"
    config_path.write_text(block + ("\n" + text.lstrip() if text.strip() else ""))


def append_codex_inline_hook(config_path: Path, config: dict[str, Any]) -> None:
    text = config_path.read_text() if config_path.exists() else ""
    text = remove_managed_toml_block(text)
    command = command_for("codex")
    block = f"""
# BEGIN phaseharness managed hook
[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = {toml_string(command)}
timeout = {config_int(config, 30, "hooks", "timeout_sec")}
statusMessage = "Checking phaseharness state"
# END phaseharness managed hook
"""
    config_path.write_text(text.rstrip() + "\n" + block.lstrip())


def install_codex_hooks(root: Path, config: dict[str, Any]) -> list[Path]:
    make_executable(root / ".phaseharness" / "hooks" / "codex-stop.sh")
    config_path = root / ".codex" / "config.toml"
    hooks_path = root / ".codex" / "hooks.json"
    ensure_codex_feature_flag(config_path)
    ensure_codex_permissions(config_path, config)
    changed = [config_path]

    if hooks_path.exists() or not has_inline_codex_hooks(config_path):
        data = load_json_object(hooks_path)
        merge_stop_hook(data, hook_entry("codex", config))
        write_json(hooks_path, data)
        changed.append(hooks_path)
        return changed

    append_codex_inline_hook(config_path, config)
    return changed


def link_or_copy_skill(root: Path, target: Path) -> Path:
    source = root / ".phaseharness" / "skills" / "phaseharness"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source.resolve():
            return target
        if target.is_dir() and not target.is_symlink():
            shutil.copytree(source, target, dirs_exist_ok=True)
            return target
        return target
    try:
        rel_source = Path("..") / ".." / ".phaseharness" / "skills" / "phaseharness"
        target.symlink_to(rel_source, target_is_directory=True)
    except OSError:
        shutil.copytree(source, target)
    return target


def install_skill_bridges(root: Path) -> list[Path]:
    return [
        link_or_copy_skill(root, root / ".claude" / "skills" / "phaseharness"),
        link_or_copy_skill(root, root / ".agents" / "skills" / "phaseharness"),
    ]


def canonical_subagent_prompt(root: Path, item: dict[str, str]) -> str:
    source = root / ".phaseharness" / "subagents" / item["file"]
    body = source.read_text()
    return (
        "You are a provider-native phaseharness subagent.\n\n"
        "Only use these instructions when the parent session explicitly delegates "
        "an active phaseharness run phase to you. Read `.phaseharness/runs/<run-id>/state.json` "
        "and the phase artifacts before acting. Preserve the file-state contract and "
        "do not start or activate runs yourself.\n\n"
        f"{body.rstrip()}\n"
    )


def write_claude_subagent(root: Path, item: dict[str, str], config: dict[str, Any]) -> Path:
    target = root / ".claude" / "agents" / f"{item['claude_name']}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    subagent_config = nested_config(config, "permissions", "claude", "subagents")
    frontmatter = {
        "name": item["claude_name"],
        "description": item["description"],
        "model": "inherit",
        **subagent_config,
    }
    content = (
        "---\n"
        + "".join(f"{key}: {yaml_frontmatter_value(value)}\n" for key, value in frontmatter.items())
        +
        "---\n\n"
        f"{canonical_subagent_prompt(root, item)}"
    )
    target.write_text(content)
    return target


def write_codex_subagent(root: Path, item: dict[str, str], config: dict[str, Any]) -> Path:
    target = root / ".codex" / "agents" / f"{item['claude_name']}.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    codex = nested_config(config, "permissions", "codex", "config")
    sandbox = nested_config(codex, "sandbox_workspace_write")
    permission_lines = [
        f"approval_policy = {toml_value(codex.get('approval_policy', 'never'))}",
        f"sandbox_mode = {toml_value(codex.get('sandbox_mode', 'danger-full-access'))}",
    ]
    for key, value in sandbox.items():
        permission_lines.append(f"sandbox_workspace_write.{key} = {toml_value(value)}")
    content = (
        f"name = {toml_string(item['codex_name'])}\n"
        f"description = {toml_string(item['description'])}\n"
        + "\n".join(permission_lines)
        + "\n"
        f"developer_instructions = {toml_literal_multiline(canonical_subagent_prompt(root, item))}\n"
    )
    target.write_text(content)
    return target


def install_subagent_bridges(root: Path, runtime: str, config: dict[str, Any]) -> list[Path]:
    changed: list[Path] = []
    for item in SUBAGENTS.values():
        if runtime in ("all", "claude"):
            changed.append(write_claude_subagent(root, item, config))
        if runtime in ("all", "codex"):
            changed.append(write_codex_subagent(root, item, config))
    return changed


def ensure_state_files(root: Path) -> list[Path]:
    state_dir = root / ".phaseharness" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    changed: list[Path] = []
    active_path = state_dir / "active.json"
    if not active_path.exists():
        write_json(
            active_path,
            {
                "schema_version": 1,
                "active_run": None,
                "activation_source": None,
                "status": "inactive",
                "session_id": None,
                "provider": None,
            },
        )
        changed.append(active_path)
    index_path = state_dir / "index.json"
    if not index_path.exists():
        write_json(index_path, {"schema_version": 1, "runs": []})
        changed.append(index_path)
    (root / ".phaseharness" / "runs").mkdir(parents=True, exist_ok=True)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Install phaseharness Stop hooks and skill bridges.")
    parser.add_argument("--runtime", choices=["all", "claude", "codex"], default="all")
    parser.add_argument("--skip-skills", action="store_true")
    parser.add_argument("--skip-subagents", action="store_true")
    args = parser.parse_args()

    root = find_project_root()
    config = load_harness_config(root)
    changed: list[Path] = ensure_state_files(root)
    if args.runtime in ("all", "claude"):
        changed.extend(install_claude_hooks(root, config))
    if args.runtime in ("all", "codex"):
        changed.extend(install_codex_hooks(root, config))
    if not args.skip_skills:
        changed.extend(install_skill_bridges(root))
    if not args.skip_subagents:
        changed.extend(install_subagent_bridges(root, args.runtime, config))

    for path in changed:
        print(path.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
