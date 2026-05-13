#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SESSION_INPUT_KEYS = [
    "session_id",
    "sessionId",
    "thread_id",
    "threadId",
    "conversation_id",
    "conversationId",
]
SESSION_ENV_KEYS = {
    "claude": ["CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"],
    "codex": ["CODEX_THREAD_ID", "CODEX_SESSION_ID"],
}


def find_project_root(input_data: dict[str, object], root_arg: str | None = None) -> Path | None:
    start = Path(str(root_arg or input_data.get("cwd") or ".")).resolve()
    if start.is_file():
        start = start.parent
    current = start
    while current != current.parent:
        if (current / ".phaseharness").is_dir():
            return current
        current = current.parent
    return None


def clean_optional(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def session_id_for(runtime: str, input_data: dict[str, object]) -> str | None:
    for key in SESSION_INPUT_KEYS:
        value = clean_optional(input_data.get(key))
        if value:
            return value
    for key in SESSION_ENV_KEYS[runtime]:
        value = clean_optional(os.environ.get(key))
        if value:
            return value
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def state_summary(root: Path) -> dict[str, Any]:
    state_dir = root / ".phaseharness" / "state"
    active_path = state_dir / "active.json"
    active = load_json(active_path)
    summary: dict[str, Any] = {
        "active_path": str(active_path.relative_to(root)),
        "active_exists": active_path.exists(),
    }
    if not active:
        return summary
    active_run = active.get("active_run")
    summary.update(
        {
            "active_run": active_run,
            "active_status": active.get("status"),
            "active_mode": active.get("mode"),
            "active_activation_source": active.get("activation_source"),
            "active_provider": active.get("provider"),
            "active_session_id": active.get("session_id"),
        }
    )
    if not active_run:
        return summary
    run_path = root / ".phaseharness" / "runs" / str(active_run) / "run.json"
    run = load_json(run_path)
    summary.update(
        {
            "run_path": str(run_path.relative_to(root)),
            "run_exists": run_path.exists(),
        }
    )
    if not run:
        return summary
    current_stage = run.get("current_stage")
    stages = run.get("stages")
    current_stage_status = None
    if isinstance(current_stage, str) and isinstance(stages, dict):
        stage_state = stages.get(current_stage)
        if isinstance(stage_state, dict):
            current_stage_status = stage_state.get("status")
    binding = run.get("session_binding")
    if not isinstance(binding, dict):
        binding = {}
    summary.update(
        {
            "run_status": run.get("status"),
            "run_mode": run.get("mode"),
            "run_activation_source": run.get("activation_source"),
            "current_stage": current_stage,
            "current_stage_status": current_stage_status,
            "blocked_by": run.get("blocked_by"),
            "run_provider": binding.get("provider") or run.get("provider"),
            "run_session_id": binding.get("session_id") or run.get("session_id"),
        }
    )
    return summary


def write_log(root: Path, runtime: str, input_data: dict[str, object], result: dict[str, Any]) -> None:
    try:
        log_dir = root / ".phaseharness" / "state" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        prompt = result.get("prompt")
        entry: dict[str, Any] = {
            "time": now_iso(),
            "runtime": runtime,
            "root": str(root),
            "hook_event_name": input_data.get("hook_event_name"),
            "session_id": input_data.get("session_id"),
            "turn_id": input_data.get("turn_id"),
            "cwd": input_data.get("cwd"),
            "stop_hook_active": input_data.get("stop_hook_active"),
            "input_keys": sorted(input_data.keys()),
            "action": result.get("action"),
            "reason": result.get("reason"),
            "error": result.get("error"),
            "stage": result.get("stage"),
            "run_id": result.get("run_id"),
            "kind": result.get("kind"),
            "prompt_chars": len(prompt) if isinstance(prompt, str) else 0,
            "state": state_summary(root),
        }
        with (log_dir / "stop-hook.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


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
    parser.add_argument("--root")
    args = parser.parse_args()

    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
        root = find_project_root(input_data, args.root)
        if root is None:
            return no_op(args.runtime)
        session_id = session_id_for(args.runtime, input_data)
        if not session_id:
            write_log(root, args.runtime, input_data, {"action": "none", "reason": "session id unavailable"})
            return no_op(args.runtime)
        runner = root / ".phaseharness" / "bin" / "phaseharness-state.py"
        result = subprocess.run(
            [
                "python3",
                str(runner),
                "next",
                "--require-auto",
                "--reprompt-running",
                "--require-session-binding",
                "--provider",
                args.runtime,
                "--session-id",
                session_id,
                "--json",
            ],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part).strip()
            log_result = {"action": "none", "error": output or f"phaseharness next failed: {result.returncode}"}
            write_log(root, args.runtime, input_data, log_result)
            return no_op(args.runtime, f"phaseharness hook error: {log_result['error']}")
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            log_result = {"action": "none", "error": f"invalid phaseharness next output: {exc}"}
            write_log(root, args.runtime, input_data, log_result)
            return no_op(args.runtime, f"phaseharness hook error: {log_result['error']}")
        if not isinstance(payload, dict):
            payload = {"action": "none", "error": "invalid phaseharness next payload"}
        write_log(root, args.runtime, input_data, payload)
        if payload.get("action") != "prompt":
            return no_op(args.runtime)
        return continuation(args.runtime, str(payload.get("prompt") or ""))
    except Exception as exc:
        return no_op(args.runtime, f"phaseharness hook error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
