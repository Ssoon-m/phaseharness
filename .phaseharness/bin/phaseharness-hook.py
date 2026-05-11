#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def find_project_root(input_data: dict[str, object]) -> Path | None:
    start = Path(str(input_data.get("cwd") or ".")).resolve()
    if start.is_file():
        start = start.parent
    current = start
    while current != current.parent:
        if (current / ".phaseharness").is_dir():
            return current
        current = current.parent
    return None


def no_op(runtime: str, message: str | None = None) -> int:
    if runtime == "codex":
        payload: dict[str, object] = {"continue": True}
        if message:
            payload["systemMessage"] = message
        print(json.dumps(payload, ensure_ascii=False))
    return 0


def continuation(runtime: str, prompt: str) -> int:
    print(json.dumps({"decision": "block", "reason": prompt}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider Stop hook wrapper for phaseharness.")
    parser.add_argument("--runtime", choices=["claude", "codex"], default="claude")
    args = parser.parse_args()

    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
        root = find_project_root(input_data)
        if root is None:
            return no_op(args.runtime)
        runner = root / ".phaseharness" / "bin" / "phaseharness-state.py"
        result = subprocess.run(
            [
                "python3",
                str(runner),
                "next",
                "--require-auto",
                "--reprompt-running",
                "--json",
            ],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return no_op(args.runtime, f"phaseharness hook error: {result.stderr.strip()}")
        payload = json.loads(result.stdout or "{}")
        if payload.get("action") != "prompt":
            return no_op(args.runtime)
        return continuation(args.runtime, str(payload.get("prompt") or ""))
    except Exception as exc:
        return no_op(args.runtime, f"phaseharness hook error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
