#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from _utils import find_project_root, now_iso, save_json


STATE_PATH = Path(".agent-harness") / ".bridge-sync-state.json"
IGNORED_NAMES = {".bridge-sync-state.json"}


def iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in value.items():
            found.extend(iter_strings(key))
            found.extend(iter_strings(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(iter_strings(item))
        return found
    return []


def read_hook_input() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def fingerprint_harness(root: Path) -> str:
    harness = root / ".agent-harness"
    digest = hashlib.sha256()
    if not harness.exists():
        return ""
    for path in sorted(p for p in harness.rglob("*") if p.is_file()):
        if path.name in IGNORED_NAMES:
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_previous_fingerprint(root: Path) -> str | None:
    path = root / STATE_PATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    value = data.get("fingerprint") if isinstance(data, dict) else None
    return str(value) if value else None


def write_state(root: Path, fingerprint: str) -> None:
    save_json(
        root / STATE_PATH,
        {
            "fingerprint": fingerprint,
            "synced_at": now_iso(),
        },
    )


def event_mentions_harness(event: dict[str, Any]) -> bool:
    for value in iter_strings(event):
        normalized = value.replace("\\", "/")
        if ".agent-harness" in normalized:
            return True
    return False


def should_sync(root: Path, hook_mode: bool, event: dict[str, Any]) -> tuple[bool, str]:
    current = fingerprint_harness(root)
    if not current:
        return False, "missing .agent-harness"
    previous = read_previous_fingerprint(root)
    if not hook_mode:
        return True, "manual"
    if previous != current:
        return True, "fingerprint changed"
    if event_mentions_harness(event):
        return True, "hook event mentioned .agent-harness"
    return False, "unchanged"


def run_gen_bridges(root: Path) -> int:
    script = root / "scripts" / "gen-bridges.py"
    if not script.exists():
        print(f"phaseloop: missing {script.relative_to(root)}", file=sys.stderr)
        return 1
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate phaseloop runtime bridges when .agent-harness changes.")
    parser.add_argument("--hook", action="store_true", help="Run in Claude/Codex hook mode")
    parser.add_argument("--force", action="store_true", help="Regenerate bridges regardless of fingerprint state")
    args = parser.parse_args()

    root = find_project_root()
    event = read_hook_input() if args.hook else {}
    current = fingerprint_harness(root)
    if not current:
        return 0

    sync, reason = should_sync(root, args.hook, event)
    if args.force:
        sync, reason = True, "forced"
    if not sync:
        return 0

    code = run_gen_bridges(root)
    if code == 0:
        write_state(root, fingerprint_harness(root))
        print(f"phaseloop: regenerated runtime bridges ({reason})", file=sys.stderr)
        return 0

    print(f"phaseloop: bridge regeneration failed ({reason})", file=sys.stderr)
    return 0 if args.hook else code


if __name__ == "__main__":
    raise SystemExit(main())
