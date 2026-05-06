#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


PHASE_ORDER = ["clarify", "context_gather", "plan", "generate", "evaluate"]
SUBAGENT_FILES = {
    "clarify": "clarify.md",
    "context_gather": "context-gather.md",
    "plan": "plan.md",
    "generate": "generate.md",
    "evaluate": "evaluate.md",
}
CLAUDE_SUBAGENTS = {
    "clarify": "phaseharness-clarify",
    "context_gather": "phaseharness-context-gather",
    "plan": "phaseharness-plan",
    "generate": "phaseharness-generate",
    "evaluate": "phaseharness-evaluate",
}
CODEX_SUBAGENTS = {
    "clarify": "phaseharness_clarify",
    "context_gather": "phaseharness_context_gather",
    "plan": "phaseharness_plan",
    "generate": "phaseharness_generate",
    "evaluate": "phaseharness_evaluate",
}
DEFAULT_GENERATE_STATE = {
    "queue": [],
    "current_phase": None,
    "phase_attempts": {},
    "phase_status": {},
    "completed_phases": [],
    "failed_phases": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def find_project_root(input_data: dict[str, Any]) -> Path | None:
    start_value = input_data.get("cwd") or "."
    current = Path(str(start_value)).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness").is_dir():
            return current
        current = current.parent
    return None


def no_op(runtime: str) -> int:
    if runtime == "codex":
        print(json.dumps({"continue": True}))
    return 0


def continuation(runtime: str, reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


class Lock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        if fcntl is not None:
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise TimeoutError("phaseharness hook lock timed out")
                    time.sleep(0.05)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.handle is None:
            return
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def phase_artifact_exists(run_dir: Path, state: dict[str, Any], phase: str) -> bool:
    phase_state = state.get("phases", {}).get(phase, {})
    artifact = phase_state.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        return False
    path = run_dir / artifact
    return path.exists() and bool(path.read_text().strip())


def subagent_instructions(root: Path, phase: str) -> str:
    subagent_file = root / ".phaseharness" / "subagents" / SUBAGENT_FILES[phase]
    return subagent_file.read_text() if subagent_file.exists() else f"Complete phase: {phase}."


def generate_state(state: dict[str, Any]) -> dict[str, Any]:
    generate = state.setdefault("generate", {})
    for key, value in DEFAULT_GENERATE_STATE.items():
        if key not in generate:
            generate[key] = value.copy() if isinstance(value, (list, dict)) else value
    return generate


def loop_current(state: dict[str, Any]) -> int:
    loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
    return max(1, int(loop.get("current", 1))) if isinstance(loop, dict) else 1


def loop_max(state: dict[str, Any]) -> int:
    loop = state.get("loop") if isinstance(state.get("loop"), dict) else {}
    return max(1, int(loop.get("max", 1))) if isinstance(loop, dict) else 1


def max_attempts_per_phase(state: dict[str, Any]) -> int:
    return max(1, int(state.get("max_attempts_per_phase", 1)))


def current_implementation_phase(state: dict[str, Any]) -> str | None:
    current = generate_state(state).get("current_phase")
    return str(current) if current else None


def implementation_phase_path(run_dir: Path, phase_id: str | None) -> Path | None:
    if not phase_id:
        return None
    return run_dir / "phases" / f"{phase_id}.md"


def attempt_for_prompt(state: dict[str, Any], phase: str) -> int:
    if phase == "generate":
        current = current_implementation_phase(state)
        if current:
            attempts = generate_state(state).setdefault("phase_attempts", {})
            return int(attempts.get(current, 0))
    return int(state.get("attempts", {}).get(phase, 0))


def build_prompt(root: Path, run_dir: Path, state: dict[str, Any], phase: str) -> str:
    template_path = root / ".phaseharness" / "prompts" / "continuation.md"
    template = template_path.read_text()
    phase_state = state["phases"][phase]
    artifact = phase_state["artifact"]
    attempt = attempt_for_prompt(state, phase)
    resume = state.get("resume") if isinstance(state.get("resume"), dict) else {}
    resume_summary = str(resume.get("summary") or "none") if isinstance(resume, dict) else "none"
    impl_phase = current_implementation_phase(state)
    impl_path = implementation_phase_path(run_dir, impl_phase)
    return (
        template.replace("{{RUN_ID}}", str(state["run_id"]))
        .replace("{{PHASE}}", phase)
        .replace("{{STATE_PATH}}", str((run_dir / "state.json").relative_to(root)))
        .replace("{{ARTIFACT_PATH}}", str((run_dir / artifact).relative_to(root)))
        .replace("{{ATTEMPT}}", str(attempt))
        .replace("{{MAX_ATTEMPTS_PER_PHASE}}", str(max_attempts_per_phase(state)))
        .replace("{{LOOP_CURRENT}}", str(loop_current(state)))
        .replace("{{LOOP_COUNT}}", str(loop_max(state)))
        .replace("{{COMMIT_MODE}}", str(state.get("commit_mode", "none")))
        .replace("{{CLAUDE_SUBAGENT}}", CLAUDE_SUBAGENTS.get(phase, "none"))
        .replace("{{CODEX_SUBAGENT}}", CODEX_SUBAGENTS.get(phase, "none"))
        .replace("{{IMPLEMENTATION_PHASE}}", impl_phase or "none")
        .replace("{{IMPLEMENTATION_PHASE_PATH}}", str(impl_path.relative_to(root)) if impl_path else "none")
        .replace("{{RESUME_SUMMARY}}", resume_summary)
        .replace("{{SUBAGENT_INSTRUCTIONS}}", subagent_instructions(root, phase))
    )


def clear_active(root: Path) -> None:
    save_json(
        root / ".phaseharness" / "state" / "active.json",
        {
            "schema_version": 1,
            "active_run": None,
            "activation_source": None,
            "status": "inactive",
            "session_id": None,
            "provider": None,
            "updated_at": now_iso(),
        },
    )


def update_index(root: Path, run_id: str, status: str) -> None:
    path = root / ".phaseharness" / "state" / "index.json"
    index = load_json(path, {"schema_version": 1, "runs": []})
    for item in index.get("runs", []):
        if isinstance(item, dict) and item.get("run_id") == run_id:
            item["status"] = status
            item["updated_at"] = now_iso()
            break
    save_json(path, index)


def commit_helper_command(
    state: dict[str, Any],
    key: str,
    mode: str,
    implementation_phase: str | None = None,
) -> list[str]:
    run_id = str(state.get("run_id"))
    command = [
        "python3",
        ".phaseharness/bin/commit-result.py",
        run_id,
        "--mode",
        mode,
    ]
    if implementation_phase:
        command.extend(["--implementation-phase", implementation_phase])
    if mode == "implementation-phase":
        command.append("--allow-head-move")
    command.extend(["--record-state-key", key])
    return command


def shell_join(command: list[str]) -> str:
    return " ".join(command)


def commit_skill_prompt(
    state: dict[str, Any],
    key: str,
    mode: str,
    implementation_phase: str | None,
    command: list[str],
) -> str:
    phase_detail = implementation_phase or "final"
    return (
        "Phaseharness commit mode requires a product commit through the `commit` skill.\n\n"
        f"Run id: `{state.get('run_id')}`\n"
        f"Commit step: `{key}`\n"
        f"Commit helper mode: `{mode}`\n"
        f"Implementation phase: `{phase_detail}`\n\n"
        "Use the provider `commit` skill now. Follow its inspection and staging rules. "
        "For this phaseharness-managed commit, run the helper command below from the "
        "project root instead of hand-staging paths:\n\n"
        "```bash\n"
        f"{shell_join(command)}\n"
        "```\n\n"
        "Do not push. Do not include `.phaseharness/` runtime state or provider bridge "
        "files in the product commit. Stop after the helper records the commit result; "
        "the next Stop hook will continue the run from file state."
    )


def maybe_request_commit(
    run_dir: Path,
    state: dict[str, Any],
    key: str,
    mode: str,
    implementation_phase: str | None = None,
) -> str | None:
    commits = state.setdefault("commits", {})
    existing = commits.get(key)
    if isinstance(existing, dict) and existing.get("status") == "completed":
        return None
    command = commit_helper_command(state, key, mode, implementation_phase)
    if not (isinstance(existing, dict) and existing.get("status") == "pending"):
        commits[key] = {
            "mode": mode,
            "status": "pending",
            "implementation_phase": implementation_phase,
            "command": shell_join(command),
            "updated_at": now_iso(),
        }
        save_json(run_dir / "state.json", state)
    return commit_skill_prompt(state, key, mode, implementation_phase, command)


def maybe_commit_implementation_phase(root: Path, run_dir: Path, state: dict[str, Any], phase_id: str) -> str | None:
    if str(state.get("commit_mode", "none")) != "phase":
        return None
    key = f"implementation_{phase_id}"
    return maybe_request_commit(run_dir, state, key, "implementation-phase", phase_id)


def maybe_commit_final(run_dir: Path, state: dict[str, Any]) -> str | None:
    if str(state.get("commit_mode", "none")) != "final":
        return None
    return maybe_request_commit(run_dir, state, "final", "completed")


def mark_run_finished(root: Path, run_dir: Path, state: dict[str, Any], status: str) -> str | None:
    state["status"] = status
    state["completed_at" if status == "completed" else "failed_at"] = now_iso()
    save_json(run_dir / "state.json", state)
    update_index(root, str(state.get("run_id")), state.get("status", status))
    clear_active(root)
    return None


def phase_status(state: dict[str, Any], phase: str) -> str:
    value = state.get("phases", {}).get(phase, {}).get("status", "pending")
    return str(value)


def set_phase_status(state: dict[str, Any], phase: str, status: str, message: str | None = None) -> None:
    phase_state = state.setdefault("phases", {}).setdefault(phase, {})
    phase_state["status"] = status
    phase_state["updated_at"] = now_iso()
    if status == "completed":
        phase_state["completed_at"] = now_iso()
    else:
        phase_state.pop("completed_at", None)
    if message:
        phase_state["error_message"] = message


def increment_attempt(state: dict[str, Any], phase: str) -> int:
    attempts = state.setdefault("attempts", {})
    attempts[phase] = int(attempts.get(phase, 0)) + 1
    return int(attempts[phase])


def set_inflight(state: dict[str, Any], phase: str, input_data: dict[str, Any]) -> None:
    state["inflight"] = {
        "phase": phase,
        "implementation_phase": current_implementation_phase(state),
        "loop": loop_current(state),
        "session_id": input_data.get("session_id"),
        "turn_id": input_data.get("turn_id"),
        "started_at": now_iso(),
    }


def session_snapshot(runtime: str, input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": runtime,
        "session_id": input_data.get("session_id"),
        "turn_id": input_data.get("turn_id"),
        "transcript_path": input_data.get("transcript_path"),
        "model": input_data.get("model"),
        "updated_at": now_iso(),
    }


def bind_or_check_session(
    root: Path,
    run_dir: Path,
    state: dict[str, Any],
    active: dict[str, Any],
    runtime: str,
    input_data: dict[str, Any],
) -> bool:
    incoming = session_snapshot(runtime, input_data)
    incoming_session_id = incoming.get("session_id")
    current = state.get("session") if isinstance(state.get("session"), dict) else {}
    current_session_id = current.get("session_id") if isinstance(current, dict) else None
    resume = state.get("resume") if isinstance(state.get("resume"), dict) else {}
    resume_requested = resume.get("status") == "requested" if isinstance(resume, dict) else False

    if current_session_id and incoming_session_id and current_session_id != incoming_session_id and not resume_requested:
        return False

    if not current_session_id or resume_requested:
        history = state.setdefault("session_history", [])
        if current_session_id:
            history.append({**current, "ended_at": now_iso(), "reason": "resume"})
        state["session"] = incoming
        state["resume"] = {
            "status": "active" if resume_requested else "none",
            "requested_at": resume.get("requested_at") if isinstance(resume, dict) else None,
            "resumed_at": now_iso() if resume_requested else None,
            "summary": resume.get("summary", "") if isinstance(resume, dict) else "",
        }
        active["session_id"] = incoming_session_id
        active["provider"] = runtime
        active["updated_at"] = now_iso()
        save_json(root / ".phaseharness" / "state" / "active.json", active)
        save_json(run_dir / "state.json", state)
    elif incoming_session_id == current_session_id:
        state["session"] = {**current, **incoming}
        save_json(run_dir / "state.json", state)
    return True


def current_or_first_pending(state: dict[str, Any]) -> str:
    current = str(state.get("current_phase") or "clarify")
    if current in PHASE_ORDER:
        return current
    for phase in PHASE_ORDER:
        if phase_status(state, phase) != "completed":
            return phase
    return "evaluate"


def next_phase(phase: str) -> str | None:
    try:
        index = PHASE_ORDER.index(phase)
    except ValueError:
        return None
    if index + 1 >= len(PHASE_ORDER):
        return None
    return PHASE_ORDER[index + 1]


def discover_implementation_phases(run_dir: Path) -> list[str]:
    phase_dir = run_dir / "phases"
    if not phase_dir.exists():
        return []
    return [path.stem for path in sorted(phase_dir.glob("phase-*.md")) if path.is_file()]


def sync_generate_queue(run_dir: Path, state: dict[str, Any]) -> list[str]:
    generate = generate_state(state)
    queue = generate.setdefault("queue", [])
    statuses = generate.setdefault("phase_status", {})
    for phase_id in discover_implementation_phases(run_dir):
        if phase_id not in queue:
            queue.append(phase_id)
        statuses.setdefault(phase_id, "pending")
    return [str(item) for item in queue]


def set_implementation_phase_status(
    state: dict[str, Any],
    phase_id: str,
    status: str,
    message: str | None = None,
) -> None:
    generate = generate_state(state)
    statuses = generate.setdefault("phase_status", {})
    statuses[phase_id] = status
    generate["updated_at"] = now_iso()
    if status == "completed":
        completed = generate.setdefault("completed_phases", [])
        if phase_id not in completed:
            completed.append(phase_id)
    if status == "error":
        failed = generate.setdefault("failed_phases", [])
        if phase_id not in failed:
            failed.append(phase_id)
    if message:
        errors = generate.setdefault("phase_errors", {})
        errors[phase_id] = message


def increment_implementation_attempt(state: dict[str, Any], phase_id: str) -> int:
    attempts = generate_state(state).setdefault("phase_attempts", {})
    attempts[phase_id] = int(attempts.get(phase_id, 0)) + 1
    return int(attempts[phase_id])


def next_pending_implementation_phase(run_dir: Path, state: dict[str, Any]) -> str | None:
    queue = sync_generate_queue(run_dir, state)
    statuses = generate_state(state).setdefault("phase_status", {})
    for phase_id in queue:
        if statuses.get(phase_id, "pending") != "completed":
            return phase_id
    return None


def output_record_path(run_dir: Path, input_data: dict[str, Any]) -> Path | None:
    turn_id = input_data.get("turn_id") or input_data.get("session_id")
    if not turn_id:
        return None
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(turn_id))
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%dT%H%M%S%f%z")
    return run_dir / "outputs" / f"stop-{safe}-{stamp}.json"


def start_or_retry_top_level_phase(
    root: Path,
    run_dir: Path,
    state: dict[str, Any],
    state_path: Path,
    phase: str,
    status: str,
    input_data: dict[str, Any],
) -> str | None:
    attempts = int(state.get("attempts", {}).get(phase, 0))
    budget = max_attempts_per_phase(state)
    if status == "error" and attempts >= budget:
        mark_run_finished(root, run_dir, state, "error")
        return None
    if status == "running" and attempts >= budget:
        set_phase_status(state, phase, "error", "phase did not complete before attempt budget was exhausted")
        mark_run_finished(root, run_dir, state, "error")
        return None
    increment_attempt(state, phase)
    set_phase_status(state, phase, "running")
    set_inflight(state, phase, input_data)
    save_json(state_path, state)
    return build_prompt(root, run_dir, state, phase)


def start_or_retry_implementation_phase(
    root: Path,
    run_dir: Path,
    state: dict[str, Any],
    state_path: Path,
    phase_id: str,
    status: str,
    input_data: dict[str, Any],
) -> str | None:
    phase_path = implementation_phase_path(run_dir, phase_id)
    if phase_path is None or not phase_path.exists():
        set_implementation_phase_status(state, phase_id, "error", "implementation phase file is missing")
        set_phase_status(state, "generate", "error", f"{phase_id} file is missing")
        mark_run_finished(root, run_dir, state, "error")
        return None
    attempts = int(generate_state(state).setdefault("phase_attempts", {}).get(phase_id, 0))
    budget = max_attempts_per_phase(state)
    if status == "error" and attempts >= budget:
        set_phase_status(state, "generate", "error", f"{phase_id} exhausted attempt budget")
        mark_run_finished(root, run_dir, state, "error")
        return None
    if status == "running" and attempts >= budget:
        set_implementation_phase_status(state, phase_id, "error", "implementation phase did not complete before attempt budget was exhausted")
        set_phase_status(state, "generate", "error", f"{phase_id} exhausted attempt budget")
        mark_run_finished(root, run_dir, state, "error")
        return None
    generate_state(state)["current_phase"] = phase_id
    increment_implementation_attempt(state, phase_id)
    set_implementation_phase_status(state, phase_id, "running")
    set_phase_status(state, "generate", "running")
    state["current_phase"] = "generate"
    set_inflight(state, "generate", input_data)
    save_json(state_path, state)
    return build_prompt(root, run_dir, state, "generate")


def handle_generate(
    root: Path,
    run_dir: Path,
    state: dict[str, Any],
    state_path: Path,
    input_data: dict[str, Any],
) -> str | None:
    queue = sync_generate_queue(run_dir, state)
    if not queue:
        set_phase_status(state, "generate", "error", "plan completed but no implementation phase files were queued")
        mark_run_finished(root, run_dir, state, "error")
        return None

    generate = generate_state(state)
    statuses = generate.setdefault("phase_status", {})
    current = current_implementation_phase(state)
    if current:
        status = str(statuses.get(current, "pending"))
        if status == "completed":
            if not phase_artifact_exists(run_dir, state, "generate"):
                set_phase_status(state, "generate", "error", "implementation phase completed but generate artifact is missing")
                mark_run_finished(root, run_dir, state, "error")
                return None
            commit_prompt = maybe_commit_implementation_phase(root, run_dir, state, current)
            if commit_prompt:
                return commit_prompt
            generate["current_phase"] = None
            save_json(state_path, state)
        elif status in ("pending", "running", "error"):
            return start_or_retry_implementation_phase(root, run_dir, state, state_path, current, status, input_data)

    next_id = next_pending_implementation_phase(run_dir, state)
    if next_id:
        status = str(generate_state(state).setdefault("phase_status", {}).get(next_id, "pending"))
        return start_or_retry_implementation_phase(root, run_dir, state, state_path, next_id, status, input_data)

    set_phase_status(state, "generate", "completed")
    state["current_phase"] = "evaluate"
    save_json(state_path, state)
    return start_or_retry_top_level_phase(root, run_dir, state, state_path, "evaluate", phase_status(state, "evaluate"), input_data)


def reset_for_next_loop(run_dir: Path, state: dict[str, Any]) -> bool:
    sync_generate_queue(run_dir, state)
    next_id = next_pending_implementation_phase(run_dir, state)
    if not next_id:
        return False
    loop = state.setdefault("loop", {})
    loop["current"] = loop_current(state) + 1
    generate = generate_state(state)
    generate["current_phase"] = None
    set_phase_status(state, "generate", "pending")
    set_phase_status(state, "evaluate", "pending")
    state["evaluation"] = {
        "status": "pending",
        "updated_at": now_iso(),
    }
    state["current_phase"] = "generate"
    return True


def handle_evaluate_completed(
    root: Path,
    run_dir: Path,
    state: dict[str, Any],
    state_path: Path,
    input_data: dict[str, Any],
) -> str | None:
    if not phase_artifact_exists(run_dir, state, "evaluate"):
        set_phase_status(state, "evaluate", "error", "evaluate completed but artifact is missing")
        mark_run_finished(root, run_dir, state, "error")
        return None
    evaluation_status = state.get("evaluation", {}).get("status")
    if evaluation_status in ("pass", "warn"):
        commit_prompt = maybe_commit_final(run_dir, state)
        if commit_prompt:
            return commit_prompt
        return mark_run_finished(root, run_dir, state, "completed")
    if evaluation_status == "fail":
        if loop_current(state) >= loop_max(state):
            mark_run_finished(root, run_dir, state, "error")
            return None
        if not reset_for_next_loop(run_dir, state):
            set_phase_status(state, "evaluate", "error", "evaluate failed but no follow-up implementation phase was queued")
            mark_run_finished(root, run_dir, state, "error")
            return None
        save_json(state_path, state)
        return handle_generate(root, run_dir, state, state_path, input_data)
    set_phase_status(state, "evaluate", "error", "evaluate completed without pass/warn/fail status")
    mark_run_finished(root, run_dir, state, "error")
    return None


def decide(root: Path, input_data: dict[str, Any], runtime: str) -> str | None:
    active_path = root / ".phaseharness" / "state" / "active.json"
    active = load_json(active_path, {"status": "inactive"})
    if active.get("status") != "active":
        return None
    if active.get("activation_source") != "phaseharness_skill":
        return None
    run_id = active.get("active_run")
    if not run_id:
        return None

    run_dir = root / ".phaseharness" / "runs" / str(run_id)
    state_path = run_dir / "state.json"
    if not state_path.exists():
        clear_active(root)
        return None

    state = load_json(state_path)
    if state.get("activation_source") != "phaseharness_skill":
        return None
    if state.get("status") in ("waiting_user", "completed", "error") or state.get("needs_user"):
        return None
    if state.get("status") != "active":
        return None
    if not bind_or_check_session(root, run_dir, state, active, runtime, input_data):
        return None

    phase = current_or_first_pending(state)
    status = phase_status(state, phase)

    if phase == "generate":
        return handle_generate(root, run_dir, state, state_path, input_data)

    if phase == "evaluate" and status == "completed":
        return handle_evaluate_completed(root, run_dir, state, state_path, input_data)

    if status == "completed":
        if not phase_artifact_exists(run_dir, state, phase):
            set_phase_status(state, phase, "error", "phase was completed but artifact is missing")
            status = "error"
        else:
            next_name = next_phase(phase)
            if next_name is None:
                return handle_evaluate_completed(root, run_dir, state, state_path, input_data)
            phase = next_name
            state["current_phase"] = phase
            status = phase_status(state, phase)
            if phase == "generate":
                return handle_generate(root, run_dir, state, state_path, input_data)
            if phase == "evaluate" and status == "completed":
                return handle_evaluate_completed(root, run_dir, state, state_path, input_data)

    if status in ("pending", "error"):
        return start_or_retry_top_level_phase(root, run_dir, state, state_path, phase, status, input_data)

    if status == "running":
        return start_or_retry_top_level_phase(root, run_dir, state, state_path, phase, status, input_data)

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Phaseharness Stop hook state machine.")
    parser.add_argument("--runtime", choices=["claude", "codex"], default="claude")
    args = parser.parse_args()

    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
        root = find_project_root(input_data)
        if root is None:
            return no_op(args.runtime)
        with Lock(root / ".phaseharness" / "state" / "hook.lock"):
            prompt = decide(root, input_data, args.runtime)
            if not prompt:
                return no_op(args.runtime)
            record_path = output_record_path(root / ".phaseharness" / "runs" / load_json(root / ".phaseharness" / "state" / "active.json").get("active_run", ""), input_data)
            if record_path is not None:
                save_json(record_path, {"created_at": now_iso(), "runtime": args.runtime, "prompt": prompt})
            return continuation(args.runtime, prompt)
    except Exception as exc:
        if args.runtime == "codex":
            print(json.dumps({"continue": True, "systemMessage": f"phaseharness hook error: {exc}"}))
            return 0
        print(f"phaseharness hook error: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
