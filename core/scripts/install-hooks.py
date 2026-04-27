#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path
from typing import Any

from _utils import find_project_root


HOOK_ID = "phaseloop-sync-bridges"
HOOK_TIMEOUT_SEC = 30


CLAUDE_WRAPPER = """#!/usr/bin/env sh
set -eu

hook_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
root="$(dirname "$(dirname "$hook_dir")")"
exec python3 "$root/scripts/sync-bridges.py" --hook
"""


CODEX_WRAPPER = """#!/usr/bin/env sh
set -eu

hook_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
root="$(dirname "$(dirname "$hook_dir")")"
exec python3 "$root/scripts/sync-bridges.py" --hook
"""


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def hook_command(runtime: str) -> str:
    if runtime == "claude":
        return "sh -c 'd=\"${CLAUDE_PROJECT_DIR:-$PWD}\"; while [ \"$d\" != \"/\" ]; do f=\"$d/.claude/hooks/phaseloop-sync-bridges.sh\"; if [ -x \"$f\" ]; then exec \"$f\"; fi; d=\"$(dirname \"$d\")\"; done; exit 0'"
    if runtime == "codex":
        return "sh -c 'd=\"$PWD\"; while [ \"$d\" != \"/\" ]; do f=\"$d/.codex/hooks/phaseloop-sync-bridges.sh\"; if [ -x \"$f\" ]; then exec \"$f\"; fi; d=\"$(dirname \"$d\")\"; done; exit 0'"
    raise ValueError(runtime)


def hook_entry(runtime: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": "command",
        "command": hook_command(runtime),
        "timeout": HOOK_TIMEOUT_SEC,
    }
    if runtime == "codex":
        entry["statusMessage"] = "Syncing phaseloop bridges"
    return entry


def command_is_phaseloop(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    return isinstance(command, str) and HOOK_ID in command


def merge_hook_group(data: dict[str, Any], event: str, matcher: str, entry: dict[str, Any]) -> None:
    hooks_root = data.setdefault("hooks", {})
    if not isinstance(hooks_root, dict):
        raise RuntimeError("hooks must be an object")
    groups = hooks_root.setdefault(event, [])
    if not isinstance(groups, list):
        raise RuntimeError(f"hooks.{event} must be a list")

    target_group: dict[str, Any] | None = None
    for group in groups:
        if isinstance(group, dict) and str(group.get("matcher", "")) == matcher:
            target_group = group
            break

    if target_group is None:
        target_group = {"matcher": matcher, "hooks": []}
        groups.append(target_group)

    entries = target_group.setdefault("hooks", [])
    if not isinstance(entries, list):
        raise RuntimeError(f"hooks.{event}[matcher={matcher}].hooks must be a list")
    entries[:] = [item for item in entries if not command_is_phaseloop(item)]
    entries.append(entry)


def install_claude_hooks(root: Path) -> list[Path]:
    wrapper = root / ".claude" / "hooks" / "phaseloop-sync-bridges.sh"
    write_executable(wrapper, CLAUDE_WRAPPER)

    settings_path = root / ".claude" / "settings.json"
    data = load_json_object(settings_path)
    entry = hook_entry("claude")
    merge_hook_group(data, "SessionStart", "startup|resume", entry)
    merge_hook_group(data, "PostToolUse", "Bash|Edit|Write|MultiEdit", entry)
    write_json(settings_path, data)
    return [wrapper, settings_path]


def has_inline_codex_hooks(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text()
    return bool(re.search(r"(?m)^\s*\[hooks\]\s*$|^\s*\[\[hooks\.", text))


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


def remove_managed_toml_block(text: str) -> str:
    pattern = re.compile(
        r"\n?# BEGIN phaseloop managed hook\n.*?# END phaseloop managed hook\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", text).rstrip() + "\n"


def append_codex_inline_hooks(config_path: Path) -> None:
    text = config_path.read_text() if config_path.exists() else ""
    text = remove_managed_toml_block(text)
    command = hook_command("codex")
    block = f"""
# BEGIN phaseloop managed hook
[[hooks.SessionStart]]
matcher = "startup|resume"
[[hooks.SessionStart.hooks]]
type = "command"
command = {toml_string(command)}
timeout = {HOOK_TIMEOUT_SEC}
statusMessage = "Syncing phaseloop bridges"

[[hooks.PostToolUse]]
matcher = "Bash|apply_patch|Edit|Write"
[[hooks.PostToolUse.hooks]]
type = "command"
command = {toml_string(command)}
timeout = {HOOK_TIMEOUT_SEC}
statusMessage = "Syncing phaseloop bridges"
# END phaseloop managed hook
"""
    config_path.write_text(text.rstrip() + "\n" + block.lstrip())


def install_codex_hooks(root: Path) -> list[Path]:
    wrapper = root / ".codex" / "hooks" / "phaseloop-sync-bridges.sh"
    write_executable(wrapper, CODEX_WRAPPER)

    config_path = root / ".codex" / "config.toml"
    hooks_path = root / ".codex" / "hooks.json"
    ensure_codex_feature_flag(config_path)

    changed = [wrapper, config_path]

    if hooks_path.exists() or not has_inline_codex_hooks(config_path):
        data = load_json_object(hooks_path)
        entry = hook_entry("codex")
        merge_hook_group(data, "SessionStart", "startup|resume", entry)
        merge_hook_group(data, "PostToolUse", "Bash|apply_patch|Edit|Write", entry)
        write_json(hooks_path, data)
        changed.append(hooks_path)
        return changed

    if has_inline_codex_hooks(config_path):
        append_codex_inline_hooks(config_path)
        return changed

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Install phaseloop bridge-sync hooks for Claude Code and Codex.")
    parser.add_argument("--runtime", choices=["all", "claude", "codex"], default="all")
    args = parser.parse_args()

    root = find_project_root()
    changed: list[Path] = []
    if args.runtime in ("all", "claude"):
        changed.extend(install_claude_hooks(root))
    if args.runtime in ("all", "codex"):
        changed.extend(install_codex_hooks(root))

    for path in changed:
        print(path.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
