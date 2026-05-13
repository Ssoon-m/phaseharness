#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - phaseharness hooks currently target Unix-like shells.
    fcntl = None


STAGES = ["clarify", "context_gather", "plan", "generate", "evaluate"]
USER_WAIT_STAGE = "clarify"
STAGE_SKILLS = {
    "clarify": "clarify",
    "context_gather": "context-gather",
    "plan": "plan",
    "generate": "generate",
    "evaluate": "evaluate",
}
ARTIFACTS = {
    "clarify": "artifacts/clarify.md",
    "context_gather": "artifacts/context.md",
    "plan": "artifacts/plan.md",
    "generate": "artifacts/generate.md",
    "evaluate": "artifacts/evaluate.md",
}
COMMIT_MODES = ["none", "phase", "final"]
COMMIT_TERMINAL_STATUSES = {"committed", "no_changes", "skipped"}
PROVIDERS = ["codex", "claude"]
STATE_LOCKED_COMMANDS = {
    "start",
    "start-new",
    "status",
    "next",
    "set-stage",
    "set-generate-phase",
    "set-commit",
    "wait-user",
    "pause",
    "resume",
    "park-active",
    "clear-active",
}
SESSION_ENV_KEYS = {
    "codex": ["CODEX_THREAD_ID", "CODEX_SESSION_ID"],
    "claude": ["CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"],
}
RUNTIME_SKIP_PREFIXES = [
    ".phaseharness/runs/",
    ".phaseharness/state/",
    ".phaseharness/prompts/.generated/",
    ".claude/",
    ".codex/",
    ".agents/",
    ".claude/skills/",
    ".agents/skills/",
    ".codex/agents/",
    ".claude/agents/",
]
RUNTIME_SKIP_EXACT = {
    ".claude/settings.json",
    ".codex/config.toml",
    ".codex/hooks.json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def harness_dir(root: Path) -> Path:
    return root / ".phaseharness"


@contextmanager
def state_lock(root: Path):
    if fcntl is None:
        raise RuntimeError("phaseharness state locking requires fcntl")
    lock_dir = harness_dir(root) / "state"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "phaseharness.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def runs_dir(root: Path) -> Path:
    return harness_dir(root) / "runs"


def active_path(root: Path) -> Path:
    return harness_dir(root) / "state" / "active.json"


def index_path(root: Path) -> Path:
    return harness_dir(root) / "state" / "index.json"


def run_dir(root: Path, run_id: str) -> Path:
    return runs_dir(root) / run_id


def run_path(root: Path, run_id: str) -> Path:
    return run_dir(root, run_id) / "run.json"


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def ensure_state_files(root: Path) -> None:
    save_json_if_missing(
        active_path(root),
        {
            "schema_version": 1,
            "active_run": None,
            "activation_source": None,
            "mode": None,
            "status": "inactive",
            "provider": None,
            "session_id": None,
            "bound_at": None,
            "bound_source": None,
            "worktree_root": None,
            "updated_at": now_iso(),
        },
    )
    save_json_if_missing(index_path(root), {"schema_version": 1, "runs": []})
    runs_dir(root).mkdir(parents=True, exist_ok=True)


def save_json_if_missing(path: Path, data: Any) -> None:
    if not path.exists():
        save_json(path, data)


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True)


def git_head(root: Path) -> str:
    result = git(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def git_branch(root: Path) -> str:
    result = git(root, "branch", "--show-current")
    return result.stdout.strip() if result.returncode == 0 else ""


def git_dirty_paths(root: Path) -> list[str]:
    result = git(root, "status", "--porcelain=v1", "-z")
    if result.returncode != 0:
        return []
    paths: set[str] = set()
    chunks = result.stdout.split("\0")
    index = 0
    while index < len(chunks):
        raw = chunks[index]
        index += 1
        if not raw or len(raw) < 4:
            continue
        status = raw[:2]
        path = raw[3:]
        if path:
            paths.add(path)
        if ("R" in status or "C" in status) and index < len(chunks) and chunks[index]:
            paths.add(chunks[index])
            index += 1
    return sorted(paths)


def normalize_stage(value: str) -> str:
    stage = value.replace("-", "_")
    if stage not in STAGES:
        raise argparse.ArgumentTypeError(f"unknown stage: {value}")
    return stage


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "run"


def next_run_id(root: Path, request: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{slugify(request)}"
    candidate = base
    suffix = 2
    while run_path(root, candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def infer_provider(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    for provider, keys in SESSION_ENV_KEYS.items():
        if any(clean_optional(os.environ.get(key)) for key in keys):
            return provider
    return None


def infer_session_id(provider: str | None, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    providers = [provider] if provider in SESSION_ENV_KEYS else list(SESSION_ENV_KEYS)
    for item in providers:
        for key in SESSION_ENV_KEYS[item]:
            value = clean_optional(os.environ.get(key))
            if value:
                return value
    return None


def identity_from_args(args: argparse.Namespace) -> tuple[str | None, str | None]:
    provider = infer_provider(getattr(args, "provider", None))
    session_id = infer_session_id(provider, clean_optional(getattr(args, "session_id", None)))
    return provider, session_id


def build_binding(provider: str, session_id: str, source: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "session_id": session_id,
        "bound_at": now_iso(),
        "bound_source": source,
    }


def bind_state(state: dict[str, Any], provider: str, session_id: str, source: str) -> None:
    state["session_binding"] = build_binding(provider, session_id, source)


def clear_state_binding(state: dict[str, Any]) -> None:
    state["session_binding"] = None
    state["provider"] = None
    state["session_id"] = None


def state_binding(state: dict[str, Any]) -> dict[str, Any] | None:
    binding = state.get("session_binding")
    if isinstance(binding, dict) and binding.get("provider") and binding.get("session_id"):
        return binding
    provider = clean_optional(state.get("provider"))
    session_id = clean_optional(state.get("session_id"))
    if provider and session_id:
        return {"provider": provider, "session_id": session_id}
    return None


def active_binding(active: dict[str, Any]) -> dict[str, Any] | None:
    provider = clean_optional(active.get("provider"))
    session_id = clean_optional(active.get("session_id"))
    if provider and session_id:
        return {
            "provider": provider,
            "session_id": session_id,
            "bound_at": active.get("bound_at"),
            "bound_source": active.get("bound_source"),
        }
    return None


def binding_error(
    binding: dict[str, Any] | None,
    provider: str | None,
    session_id: str | None,
    require: bool,
) -> str | None:
    if not require and not (provider or session_id):
        return None
    if not provider or not session_id:
        return "session id unavailable"
    if not binding:
        return "active run has no session binding"
    if binding.get("provider") != provider or binding.get("session_id") != session_id:
        return "active run is bound to another session"
    return None


def ensure_update_allowed(state: dict[str, Any], provider: str | None, session_id: str | None) -> None:
    if state.get("mode") != "auto":
        return
    error = binding_error(state_binding(state), provider, session_id, require=True)
    if error:
        raise RuntimeError(error)


def initial_run(
    root: Path,
    run_id: str,
    request: str,
    mode: str,
    stage: str,
    loop_count: int,
    commit_mode: str,
    provider: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    binding = build_binding(provider, session_id, "start") if provider and session_id else None
    return {
        "schema_version": 1,
        "run_id": run_id,
        "request": request,
        "mode": mode,
        "activation_source": "phaseharness_skill" if mode == "auto" else "manual_skill",
        "status": "active",
        "current_stage": stage,
        "workflow": STAGES,
        "loop": {"current": 1, "max": loop_count},
        "commit_mode": commit_mode,
        "session_binding": binding,
        "worktree": {
            "root": str(root),
            "branch": git_branch(root),
        },
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "git_baseline": {
            "head": git_head(root),
            "dirty_paths": git_dirty_paths(root),
        },
        "stages": {
            item: {
                "status": "pending",
                "artifact": ARTIFACTS[item],
                "attempts": 0,
            }
            for item in STAGES
        },
        "generate": {
            "queue": [],
            "current_phase": None,
            "phase_status": {},
            "phase_attempts": {},
            "phase_dirty_baselines": {},
            "completed_phases": [],
            "failed_phases": [],
        },
        "evaluation": {"status": "pending"},
        "commits": {},
        "blocked_by": None,
        "inflight": None,
    }


def update_index(root: Path, state: dict[str, Any]) -> None:
    path = index_path(root)
    index = load_json(path, {"schema_version": 1, "runs": []})
    runs = index.setdefault("runs", [])
    existing = None
    for item in runs:
        if isinstance(item, dict) and item.get("run_id") == state.get("run_id"):
            existing = item
            break
    binding = state_binding(state) or {}
    record = {
        "run_id": state.get("run_id"),
        "request": state.get("request"),
        "mode": state.get("mode"),
        "status": state.get("status"),
        "current_stage": state.get("current_stage"),
        "loop_count": state.get("loop", {}).get("max"),
        "commit_mode": state.get("commit_mode"),
        "provider": binding.get("provider"),
        "session_id": binding.get("session_id"),
        "worktree_root": str(root),
        "created_at": state.get("created_at"),
        "updated_at": now_iso(),
    }
    if existing is None:
        runs.append(record)
    else:
        existing.update(record)
    save_json(path, index)


def save_run(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    save_json(run_path(root, str(state["run_id"])), state)
    update_index(root, state)


def set_active(root: Path, state: dict[str, Any]) -> None:
    binding = state_binding(state) or {}
    save_json(
        active_path(root),
        {
            "schema_version": 1,
            "active_run": state["run_id"],
            "activation_source": state.get("activation_source"),
            "mode": state.get("mode"),
            "status": state.get("status"),
            "provider": binding.get("provider"),
            "session_id": binding.get("session_id"),
            "bound_at": binding.get("bound_at"),
            "bound_source": binding.get("bound_source"),
            "worktree_root": None,
            "updated_at": now_iso(),
        },
    )


def clear_active(root: Path) -> None:
    save_json(
        active_path(root),
        {
            "schema_version": 1,
            "active_run": None,
            "activation_source": None,
            "mode": None,
            "status": "inactive",
            "provider": None,
            "session_id": None,
            "bound_at": None,
            "bound_source": None,
            "worktree_root": str(root),
            "updated_at": now_iso(),
        },
    )


def create_run(
    root: Path,
    run_id: str,
    request: str,
    mode: str,
    stage: str,
    loop_count: int,
    commit_mode: str,
    provider: str | None,
    session_id: str | None,
) -> dict[str, Any]:
    target_dir = run_dir(root, run_id)
    try:
        target_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RuntimeError(f"run already exists: {run_id}")
    (target_dir / "artifacts").mkdir()
    (target_dir / "phases").mkdir()
    state = initial_run(
        root,
        run_id,
        request,
        mode,
        stage,
        loop_count,
        commit_mode,
        provider if mode == "auto" else None,
        session_id if mode == "auto" else None,
    )
    save_run(root, state)
    if mode == "auto":
        set_active(root, state)
    return {
        "run_id": run_id,
        "run_path": str(run_path(root, run_id).relative_to(root)),
        "mode": mode,
        "session_binding": state.get("session_binding"),
    }


def stage_status(state: dict[str, Any], stage: str) -> str:
    return str(state.get("stages", {}).get(stage, {}).get("status", "pending"))


def set_run_waiting_user(state: dict[str, Any], kind: str, message: str | None = None, stage: str | None = None) -> None:
    state["status"] = "waiting_user"
    blocked_by: dict[str, Any] = {
        "kind": kind,
        "message": message or "",
        "created_at": now_iso(),
    }
    if stage:
        blocked_by["stage"] = stage
        blocked_by["artifact"] = ARTIFACTS[stage]
    state["blocked_by"] = blocked_by


def clear_run_waiting_user(state: dict[str, Any]) -> None:
    if state.get("status") == "waiting_user" or state.get("blocked_by"):
        state["status"] = "active"
        state["blocked_by"] = None


def waiting_user_reason(state: dict[str, Any]) -> str | None:
    if state.get("status") != "waiting_user":
        return None
    blocked_by = state.get("blocked_by")
    if isinstance(blocked_by, dict):
        message = str(blocked_by.get("message") or "").strip()
        if message:
            return message
        kind = blocked_by.get("kind")
        if kind == "clarify_user_decision":
            return "clarify is waiting for user input"
        if kind == "manual_pause":
            return "run is manually paused"
    return "run is waiting for user input"


def set_stage_status(state: dict[str, Any], stage: str, status: str, message: str | None = None) -> None:
    stage_state = state.setdefault("stages", {}).setdefault(stage, {"artifact": ARTIFACTS[stage], "attempts": 0})
    stage_state["status"] = status
    stage_state["updated_at"] = now_iso()
    if status == "running" and "started_at" not in stage_state:
        stage_state["started_at"] = now_iso()
    if status == "completed":
        stage_state["completed_at"] = now_iso()
    if message:
        stage_state["message"] = message


def increment_stage_attempt(state: dict[str, Any], stage: str) -> None:
    stage_state = state.setdefault("stages", {}).setdefault(stage, {"artifact": ARTIFACTS[stage], "attempts": 0})
    stage_state["attempts"] = int(stage_state.get("attempts", 0)) + 1


def artifact_path_for(root: Path, state: dict[str, Any], stage: str) -> Path:
    return run_dir(root, str(state["run_id"])) / state["stages"][stage]["artifact"]


def artifact_nonempty(root: Path, state: dict[str, Any], stage: str) -> bool:
    path = artifact_path_for(root, state, stage)
    return path.exists() and bool(path.read_text().strip())


def discover_phase_ids(root: Path, state: dict[str, Any]) -> list[str]:
    phase_dir = run_dir(root, str(state["run_id"])) / "phases"
    if not phase_dir.exists():
        return []
    return [path.stem for path in sorted(phase_dir.glob("phase-*.md")) if path.is_file()]


def sync_generate_queue(root: Path, state: dict[str, Any]) -> None:
    generate = state.setdefault("generate", {})
    queue = generate.setdefault("queue", [])
    statuses = generate.setdefault("phase_status", {})
    for phase_id in discover_phase_ids(root, state):
        if phase_id not in queue:
            queue.append(phase_id)
        statuses.setdefault(phase_id, "pending")


def next_pending_phase_id(root: Path, state: dict[str, Any]) -> str | None:
    sync_generate_queue(root, state)
    generate = state.setdefault("generate", {})
    statuses = generate.setdefault("phase_status", {})
    for phase_id in generate.setdefault("queue", []):
        if statuses.get(phase_id, "pending") not in COMMIT_TERMINAL_STATUSES and statuses.get(phase_id, "pending") != "completed":
            return str(phase_id)
    return None


def phase_file_path(root: Path, state: dict[str, Any], phase_id: str | None = None) -> Path | None:
    if not phase_id:
        return None
    return run_dir(root, str(state["run_id"])) / "phases" / f"{phase_id}.md"


def set_generate_phase_status(state: dict[str, Any], phase_id: str, status: str, message: str | None = None) -> None:
    generate = state.setdefault("generate", {})
    statuses = generate.setdefault("phase_status", {})
    statuses[phase_id] = status
    generate["updated_at"] = now_iso()
    if status == "completed":
        completed = generate.setdefault("completed_phases", [])
        if phase_id not in completed:
            completed.append(phase_id)
    if status in ("error", "failed"):
        failed = generate.setdefault("failed_phases", [])
        if phase_id not in failed:
            failed.append(phase_id)
    if message:
        generate.setdefault("phase_messages", {})[phase_id] = message


def increment_generate_attempt(root: Path, state: dict[str, Any], phase_id: str) -> None:
    generate = state.setdefault("generate", {})
    attempts = generate.setdefault("phase_attempts", {})
    attempts[phase_id] = int(attempts.get(phase_id, 0)) + 1
    baselines = generate.setdefault("phase_dirty_baselines", {})
    baselines.setdefault(phase_id, git_dirty_paths(root))


def path_is_runtime_or_bridge(path: str) -> bool:
    if path in RUNTIME_SKIP_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in RUNTIME_SKIP_PREFIXES)


def commit_paths(root: Path, state: dict[str, Any]) -> dict[str, list[str]]:
    dirty = set(git_dirty_paths(root))
    baseline = set(state.get("git_baseline", {}).get("dirty_paths", []))
    skipped_baseline = sorted(dirty & baseline)
    skipped_runtime = sorted(path for path in dirty if path_is_runtime_or_bridge(path))
    eligible = sorted(path for path in dirty if path not in baseline and not path_is_runtime_or_bridge(path))
    return {
        "eligible_paths": eligible,
        "skipped_baseline_paths": skipped_baseline,
        "skipped_runtime_paths": skipped_runtime,
    }


def list_block(title: str, values: list[str]) -> str:
    if not values:
        return f"{title}\n- none\n"
    return title + "\n" + "\n".join(f"- {item}" for item in values) + "\n"


def build_commit_prompt(root: Path, state: dict[str, Any], key: str, mode: str, implementation_phase: str | None) -> str:
    paths = commit_paths(root, state)
    phase_line = implementation_phase or "final"
    return (
        "# Phaseharness Commit Prompt\n\n"
        "Use the `commit` skill now. The state runner is only asking for a commit; it has not staged files and has not run `git commit`.\n\n"
        f"Run id: `{state['run_id']}`\n"
        f"Commit key: `{key}`\n"
        f"Commit mode: `{mode}`\n"
        f"Implementation phase: `{phase_line}`\n\n"
        + list_block("Eligible Paths:", paths["eligible_paths"])
        + "\n"
        + list_block("Skipped Baseline Paths:", paths["skipped_baseline_paths"])
        + "\n"
        + list_block("Skipped Runtime/Bridge Paths:", paths["skipped_runtime_paths"])
        + "\n"
        "After `commit` handles the diff, record exactly one result:\n\n"
        "```bash\n"
        f"python3 .phaseharness/bin/phaseharness-state.py set-commit {key} committed --run-id {state['run_id']}\n"
        f"python3 .phaseharness/bin/phaseharness-state.py set-commit {key} no_changes --run-id {state['run_id']} --message \"no eligible changes to commit\"\n"
        f"python3 .phaseharness/bin/phaseharness-state.py set-commit {key} skipped --run-id {state['run_id']} --message \"<unsafe or ambiguous commit scope>\"\n"
        f"python3 .phaseharness/bin/phaseharness-state.py set-commit {key} failed --run-id {state['run_id']} --message \"<failure summary>\"\n"
        "```\n\n"
        "Do not use a fixed phase-completion commit message. Inspect `git status` and the eligible diff, then write a meaningful message based on the actual change."
    )


def ensure_commit_prompt(root: Path, state: dict[str, Any], key: str, mode: str, implementation_phase: str | None) -> str | None:
    if state.get("commit_mode") == "none":
        return None
    commits = state.setdefault("commits", {})
    existing = commits.get(key)
    if isinstance(existing, dict) and existing.get("status") in COMMIT_TERMINAL_STATUSES:
        return None
    prompt = build_commit_prompt(root, state, key, mode, implementation_phase)
    commits[key] = {
        "status": "pending",
        "mode": mode,
        "implementation_phase": implementation_phase,
        "paths": commit_paths(root, state),
        "prompt": prompt,
        "updated_at": now_iso(),
    }
    return prompt


def build_stage_prompt(root: Path, state: dict[str, Any], stage: str, reprompt: bool = False) -> str:
    template_path = harness_dir(root) / "prompts" / "continuation.md"
    template = template_path.read_text()
    run_id = str(state["run_id"])
    current_phase = state.get("generate", {}).get("current_phase")
    phase_path = phase_file_path(root, state, str(current_phase) if current_phase else None)
    artifact_rel = str(Path(".phaseharness") / "runs" / run_id / state["stages"][stage]["artifact"])
    phase_rel = str(phase_path.relative_to(root)) if phase_path else "none"
    return (
        template.replace("{{RUN_ID}}", run_id)
        .replace("{{REQUEST}}", str(state.get("request", "")))
        .replace("{{STAGE}}", stage)
        .replace("{{SKILL}}", STAGE_SKILLS[stage])
        .replace("{{RUN_PATH}}", str(Path(".phaseharness") / "runs" / run_id / "run.json"))
        .replace("{{ARTIFACT_PATH}}", artifact_rel)
        .replace("{{LOOP_CURRENT}}", str(state.get("loop", {}).get("current", 1)))
        .replace("{{LOOP_COUNT}}", str(state.get("loop", {}).get("max", 1)))
        .replace("{{COMMIT_MODE}}", str(state.get("commit_mode", "none")))
        .replace("{{IMPLEMENTATION_PHASE}}", str(current_phase or "none"))
        .replace("{{IMPLEMENTATION_PHASE_PATH}}", phase_rel)
        .replace("{{REPROMPT}}", "true" if reprompt else "false")
    )


def result_none(reason: str = "no active auto run") -> dict[str, Any]:
    return {"action": "none", "reason": reason}


def result_prompt(state: dict[str, Any], stage: str, prompt: str, kind: str = "stage") -> dict[str, Any]:
    return {
        "action": "prompt",
        "kind": kind,
        "run_id": state.get("run_id"),
        "stage": stage,
        "prompt": prompt,
    }


def start_top_level_stage(root: Path, state: dict[str, Any], stage: str, reprompt: bool = False) -> dict[str, Any]:
    if not reprompt:
        increment_stage_attempt(state, stage)
    set_stage_status(state, stage, "running")
    state["status"] = "active"
    state["current_stage"] = stage
    state["inflight"] = {
        "stage": stage,
        "implementation_phase": state.get("generate", {}).get("current_phase"),
        "reprompt": reprompt,
        "updated_at": now_iso(),
    }
    save_run(root, state)
    set_active(root, state)
    return result_prompt(state, stage, build_stage_prompt(root, state, stage, reprompt=reprompt))


def start_generate_phase(root: Path, state: dict[str, Any], phase_id: str, reprompt: bool = False) -> dict[str, Any]:
    path = phase_file_path(root, state, phase_id)
    if path is None or not path.exists():
        set_generate_phase_status(state, phase_id, "error", "phase file is missing")
        set_stage_status(state, "generate", "error", f"{phase_id} file is missing")
        save_run(root, state)
        return result_none(f"{phase_id} file is missing")
    if not reprompt:
        increment_generate_attempt(root, state, phase_id)
    state.setdefault("generate", {})["current_phase"] = phase_id
    set_generate_phase_status(state, phase_id, "running")
    set_stage_status(state, "generate", "running")
    state["current_stage"] = "generate"
    state["status"] = "active"
    state["inflight"] = {
        "stage": "generate",
        "implementation_phase": phase_id,
        "reprompt": reprompt,
        "updated_at": now_iso(),
    }
    save_run(root, state)
    set_active(root, state)
    return result_prompt(state, "generate", build_stage_prompt(root, state, "generate", reprompt=reprompt))


def handle_generate(root: Path, state: dict[str, Any], reprompt_running: bool) -> dict[str, Any]:
    sync_generate_queue(root, state)
    generate = state.setdefault("generate", {})
    if not generate.get("queue"):
        set_stage_status(state, "generate", "error", "plan completed but no phase files exist")
        save_run(root, state)
        return result_none("no implementation phases")

    current = generate.get("current_phase")
    statuses = generate.setdefault("phase_status", {})
    if current:
        current = str(current)
        status = str(statuses.get(current, "pending"))
        if status == "completed":
            if not artifact_nonempty(root, state, "generate"):
                set_generate_phase_status(state, current, "error", "generate artifact is missing")
                save_run(root, state)
                return start_generate_phase(root, state, current)
            if state.get("commit_mode") == "phase":
                prompt = ensure_commit_prompt(root, state, current, "phase", current)
                if prompt:
                    save_run(root, state)
                    return result_prompt(state, "generate", prompt, kind="commit")
            generate["current_phase"] = None
            save_run(root, state)
        elif status == "running" and reprompt_running:
            return start_generate_phase(root, state, current, reprompt=True)
        elif status in ("pending", "error", "failed"):
            return start_generate_phase(root, state, current)
        else:
            return result_none(f"generate phase has status {status}")

    next_phase = next_pending_phase_id(root, state)
    if next_phase:
        return start_generate_phase(root, state, next_phase)

    set_stage_status(state, "generate", "completed")
    state["current_stage"] = "evaluate"
    save_run(root, state)
    return start_top_level_stage(root, state, "evaluate")


def finish_run(root: Path, state: dict[str, Any], status: str) -> dict[str, Any]:
    state["status"] = status
    state["blocked_by"] = None
    state["inflight"] = None
    state["completed_at" if status == "completed" else "failed_at"] = now_iso()
    save_run(root, state)
    clear_active(root)
    return result_none(f"run {status}")


def handle_evaluate_completed(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    if not artifact_nonempty(root, state, "evaluate"):
        set_stage_status(state, "evaluate", "error", "evaluate artifact is missing")
        save_run(root, state)
        return start_top_level_stage(root, state, "evaluate")

    evaluation_status = state.get("evaluation", {}).get("status")
    if evaluation_status in ("pass", "warn"):
        if state.get("commit_mode") == "final":
            prompt = ensure_commit_prompt(root, state, "final", "final", None)
            if prompt:
                save_run(root, state)
                return result_prompt(state, "evaluate", prompt, kind="commit")
        return finish_run(root, state, "completed")

    if evaluation_status == "fail":
        loop = state.setdefault("loop", {"current": 1, "max": 1})
        if int(loop.get("current", 1)) >= int(loop.get("max", 1)):
            return finish_run(root, state, "error")
        sync_generate_queue(root, state)
        if not next_pending_phase_id(root, state):
            set_stage_status(state, "evaluate", "error", "evaluate failed but no follow-up phase exists")
            save_run(root, state)
            return finish_run(root, state, "error")
        loop["current"] = int(loop.get("current", 1)) + 1
        state.setdefault("generate", {})["current_phase"] = None
        set_stage_status(state, "generate", "pending")
        set_stage_status(state, "evaluate", "pending")
        state["evaluation"] = {"status": "pending", "updated_at": now_iso()}
        state["current_stage"] = "generate"
        save_run(root, state)
        return handle_generate(root, state, reprompt_running=False)

    set_stage_status(state, "evaluate", "error", "evaluate completed without pass/warn/fail")
    save_run(root, state)
    return start_top_level_stage(root, state, "evaluate")


def first_incomplete_stage(state: dict[str, Any]) -> str:
    current = str(state.get("current_stage") or "clarify")
    if current in STAGES:
        return current
    for stage in STAGES:
        if stage_status(state, stage) != "completed":
            return stage
    return "evaluate"


def next_stage(stage: str) -> str | None:
    index = STAGES.index(stage)
    if index + 1 >= len(STAGES):
        return None
    return STAGES[index + 1]


def compute_next(
    root: Path,
    require_auto: bool,
    reprompt_running: bool,
    provider: str | None = None,
    session_id: str | None = None,
    require_session_binding: bool = False,
) -> dict[str, Any]:
    ensure_state_files(root)
    active = load_json(active_path(root), {"status": "inactive"})
    if active.get("status") not in ("active", "waiting_user") or not active.get("active_run"):
        return result_none("no active run")
    if require_auto and (active.get("mode") != "auto" or active.get("activation_source") != "phaseharness_skill"):
        return result_none("active run is not an auto phaseharness run")

    state_file = run_path(root, str(active["active_run"]))
    if not state_file.exists():
        clear_active(root)
        return result_none("active run file is missing")
    state = load_json(state_file)
    if require_auto and (state.get("mode") != "auto" or state.get("activation_source") != "phaseharness_skill"):
        return result_none("run is not auto")
    error = binding_error(
        active_binding(active) or state_binding(state),
        provider,
        session_id,
        require=require_session_binding,
    )
    if error:
        return result_none(error)
    if state.get("status") in ("completed", "error"):
        return result_none(f"run status is {state.get('status')}")
    reason = waiting_user_reason(state)
    if reason:
        return result_none(reason)
    stage = first_incomplete_stage(state)
    status = stage_status(state, stage)

    if stage == "generate":
        return handle_generate(root, state, reprompt_running=reprompt_running)

    if stage == "evaluate" and status == "completed":
        return handle_evaluate_completed(root, state)

    if status == "completed":
        if not artifact_nonempty(root, state, stage):
            set_stage_status(state, stage, "error", "stage is completed but artifact is missing")
            save_run(root, state)
            return start_top_level_stage(root, state, stage)
        following = next_stage(stage)
        if following is None:
            return handle_evaluate_completed(root, state)
        state["current_stage"] = following
        save_run(root, state)
        if following == "generate":
            return handle_generate(root, state, reprompt_running=False)
        return start_top_level_stage(root, state, following)

    if status == "running" and reprompt_running:
        return start_top_level_stage(root, state, stage, reprompt=True)
    if status in ("pending", "error"):
        return start_top_level_stage(root, state, stage)

    return result_none(f"stage status is {status}")


def active_run_id(root: Path) -> str | None:
    active = load_json(active_path(root), {"active_run": None})
    value = active.get("active_run")
    return str(value) if value else None


def resolve_run(root: Path, run_id: str | None) -> dict[str, Any]:
    target = run_id or active_run_id(root)
    if not target:
        raise RuntimeError("no run id provided and no active run exists")
    return load_json(run_path(root, target))


def command_start(args: argparse.Namespace) -> int:
    root = find_project_root()
    ensure_state_files(root)
    stage = normalize_stage(args.stage)
    mode = args.mode
    defer_session_binding = bool(getattr(args, "defer_session_binding", False))
    if defer_session_binding and mode != "auto":
        raise RuntimeError("--defer-session-binding is only valid for auto runs")
    if defer_session_binding and (args.provider or args.session_id):
        raise RuntimeError("--defer-session-binding cannot be combined with explicit session identity")
    provider, session_id = (None, None) if defer_session_binding else identity_from_args(args)
    if mode == "auto":
        active = load_json(active_path(root), {"status": "inactive"})
        if active.get("status") in ("active", "waiting_user") and active.get("active_run") and not args.force:
            raise RuntimeError(f"active run already exists: {active.get('active_run')}")
        if not defer_session_binding and (not provider or not session_id):
            raise RuntimeError("auto run requires a session binding; pass --provider and --session-id if it cannot be inferred")
    run_id = args.run_id or next_run_id(root, args.request)
    output = create_run(
        root,
        run_id,
        args.request,
        mode,
        stage,
        args.loop_count,
        args.commit_mode,
        provider,
        session_id,
    )
    print(json.dumps(output, ensure_ascii=False) if args.json else run_id)
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = find_project_root()
    ensure_state_files(root)
    active = load_json(active_path(root), {"status": "inactive"})
    if not args.json:
        print(active.get("active_run") or "inactive")
        return 0
    state = None
    if active.get("active_run") and run_path(root, str(active["active_run"])).exists():
        state = load_json(run_path(root, str(active["active_run"])))
    print(json.dumps({"active": active, "run": state}, indent=2, ensure_ascii=False))
    return 0


def command_next(args: argparse.Namespace) -> int:
    root = find_project_root()
    provider, session_id = identity_from_args(args)
    result = compute_next(
        root,
        require_auto=args.require_auto,
        reprompt_running=args.reprompt_running,
        provider=provider,
        session_id=session_id,
        require_session_binding=args.require_session_binding,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif result.get("action") == "prompt":
        print(result["prompt"])
    return 0


def command_set_stage(args: argparse.Namespace) -> int:
    root = find_project_root()
    state = resolve_run(root, args.run_id)
    provider, session_id = identity_from_args(args)
    ensure_update_allowed(state, provider, session_id)
    stage = normalize_stage(args.stage)
    set_stage_status(state, stage, args.status, args.message)
    blocked_by = state.get("blocked_by")
    if (
        isinstance(blocked_by, dict)
        and blocked_by.get("kind") == "clarify_user_decision"
        and blocked_by.get("stage") == stage
    ):
        clear_run_waiting_user(state)
    if args.evaluation_status:
        state["evaluation"] = {"status": args.evaluation_status, "updated_at": now_iso()}
    save_run(root, state)
    if state.get("mode") == "auto" and state.get("status") in ("active", "waiting_user"):
        set_active(root, state)
    print(json.dumps({"run_id": state["run_id"], "stage": stage, "status": args.status}, ensure_ascii=False))
    return 0


def command_set_generate_phase(args: argparse.Namespace) -> int:
    root = find_project_root()
    state = resolve_run(root, args.run_id)
    provider, session_id = identity_from_args(args)
    ensure_update_allowed(state, provider, session_id)
    set_generate_phase_status(state, args.phase_id, args.status, args.message)
    if args.status in ("pending", "running"):
        state.setdefault("generate", {})["current_phase"] = args.phase_id
        state["current_stage"] = "generate"
        set_stage_status(state, "generate", "running" if args.status == "running" else "pending")
    save_run(root, state)
    if state.get("mode") == "auto" and state.get("status") == "active":
        set_active(root, state)
    print(json.dumps({"run_id": state["run_id"], "phase_id": args.phase_id, "status": args.status}, ensure_ascii=False))
    return 0


def command_set_commit(args: argparse.Namespace) -> int:
    root = find_project_root()
    state = resolve_run(root, args.run_id)
    provider, session_id = identity_from_args(args)
    ensure_update_allowed(state, provider, session_id)
    commits = state.setdefault("commits", {})
    item = commits.setdefault(args.key, {})
    item["status"] = args.status
    item["message"] = args.message or ""
    item["updated_at"] = now_iso()
    if args.status in COMMIT_TERMINAL_STATUSES:
        item["completed_at"] = now_iso()
    elif args.status == "failed":
        state["status"] = "error"
    save_run(root, state)
    if state.get("status") == "error":
        clear_active(root)
    elif state.get("mode") == "auto":
        set_active(root, state)
    print(json.dumps({"run_id": state["run_id"], "commit_key": args.key, "status": args.status}, ensure_ascii=False))
    return 0


def command_wait_user(args: argparse.Namespace) -> int:
    root = find_project_root()
    state = resolve_run(root, args.run_id)
    provider, session_id = identity_from_args(args)
    ensure_update_allowed(state, provider, session_id)
    if state.get("status") in ("completed", "error"):
        raise RuntimeError(f"cannot pause a run with status {state.get('status')}")
    stage = normalize_stage(args.stage)
    if stage != USER_WAIT_STAGE:
        raise RuntimeError("wait-user is only supported for clarify")
    if state.get("current_stage") != stage:
        raise RuntimeError("wait-user can only run while clarify is the current stage")
    if stage_status(state, stage) not in ("pending", "running"):
        raise RuntimeError("wait-user requires clarify to be pending or running")
    set_run_waiting_user(state, "clarify_user_decision", args.message, stage=stage)
    save_run(root, state)
    if state.get("mode") == "auto":
        set_active(root, state)
    print(json.dumps({"run_id": state["run_id"], "status": "waiting_user", "stage": stage}, ensure_ascii=False))
    return 0


def command_pause(args: argparse.Namespace) -> int:
    root = find_project_root()
    state = resolve_run(root, args.run_id)
    provider, session_id = identity_from_args(args)
    ensure_update_allowed(state, provider, session_id)
    if state.get("status") in ("completed", "error"):
        raise RuntimeError(f"cannot pause a run with status {state.get('status')}")
    set_run_waiting_user(state, "manual_pause", args.message)
    save_run(root, state)
    if state.get("mode") == "auto":
        set_active(root, state)
    print(json.dumps({"run_id": state["run_id"], "status": "waiting_user", "kind": "manual_pause"}, ensure_ascii=False))
    return 0


def command_resume(args: argparse.Namespace) -> int:
    root = find_project_root()
    state = resolve_run(root, args.run_id)
    if state.get("status") in ("completed", "error"):
        raise RuntimeError(f"cannot resume a run with status {state.get('status')}")
    provider, session_id = identity_from_args(args)
    if state.get("mode") == "auto":
        if not provider or not session_id:
            raise RuntimeError("resume requires a session binding; pass --provider and --session-id if it cannot be inferred")
        bind_state(state, provider, session_id, "resume")
    clear_run_waiting_user(state)
    save_run(root, state)
    if state.get("mode") == "auto" and state.get("status") in ("active", "waiting_user"):
        set_active(root, state)
    print(json.dumps({"run_id": state["run_id"], "status": state["status"]}, ensure_ascii=False))
    return 0


def park_active_run(root: Path, message: str) -> dict[str, Any]:
    active = load_json(active_path(root), {"status": "inactive"})
    run_id = clean_optional(active.get("active_run"))
    output: dict[str, Any] = {
        "parked_run_id": run_id,
        "changed": False,
        "reason": "",
    }
    if active.get("status") not in ("active", "waiting_user") or not run_id:
        output["reason"] = "no active run"
    else:
        state_file = run_path(root, run_id)
        if not state_file.exists():
            clear_active(root)
            output["changed"] = True
            output["reason"] = "active run file is missing"
        else:
            state = load_json(state_file)
            if state.get("status") in ("completed", "error"):
                clear_active(root)
                output["changed"] = True
                output["reason"] = f"run status is {state.get('status')}"
            else:
                set_run_waiting_user(state, "manual_pause", message)
                clear_state_binding(state)
                save_run(root, state)
                clear_active(root)
                output["changed"] = True
                output["reason"] = "active run parked"
    return output


def command_park_active(args: argparse.Namespace) -> int:
    root = find_project_root()
    ensure_state_files(root)
    output = park_active_run(root, args.message)
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(output["reason"])
    return 0


def command_start_new(args: argparse.Namespace) -> int:
    root = find_project_root()
    ensure_state_files(root)
    stage = normalize_stage(args.stage)
    provider, session_id = identity_from_args(args)
    if not provider or not session_id:
        raise RuntimeError("auto run requires a session binding; pass --provider and --session-id if it cannot be inferred")
    run_id = args.run_id or next_run_id(root, args.request)
    if run_dir(root, run_id).exists():
        raise RuntimeError(f"run already exists: {run_id}")
    parked = park_active_run(root, args.park_message)
    started = create_run(
        root,
        run_id,
        args.request,
        "auto",
        stage,
        args.loop_count,
        args.commit_mode,
        provider,
        session_id,
    )
    output = {"parked": parked, "started": started}
    print(json.dumps(output, indent=2, ensure_ascii=False) if args.json else run_id)
    return 0


def command_clear_active(args: argparse.Namespace) -> int:
    root = find_project_root()
    ensure_state_files(root)
    clear_active(root)
    return 0


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def add_identity_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=PROVIDERS)
    parser.add_argument("--session-id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phaseharness file-state runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="create a manual or auto run")
    start.add_argument("--request", required=True)
    start.add_argument("--mode", choices=["manual", "auto"], default="auto")
    start.add_argument("--stage", default="clarify")
    start.add_argument("--run-id")
    start.add_argument("--loop-count", type=positive_int, default=1)
    start.add_argument("--commit-mode", choices=COMMIT_MODES, default="none")
    start.add_argument("--force", action="store_true")
    start.add_argument("--defer-session-binding", action="store_true")
    start.add_argument("--json", action="store_true")
    add_identity_args(start)
    start.set_defaults(func=command_start)

    start_new = sub.add_parser("start-new", help="park the active run and create a new auto run")
    start_new.add_argument("--request", required=True)
    start_new.add_argument("--stage", default="clarify")
    start_new.add_argument("--run-id")
    start_new.add_argument("--loop-count", type=positive_int, default=1)
    start_new.add_argument("--commit-mode", choices=COMMIT_MODES, default="none")
    start_new.add_argument("--park-message", default="manual pause before starting a new phaseharness run")
    start_new.add_argument("--json", action="store_true")
    add_identity_args(start_new)
    start_new.set_defaults(func=command_start_new)

    status = sub.add_parser("status", help="print active run status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    next_cmd = sub.add_parser("next", help="print the next continuation prompt")
    next_cmd.add_argument("--require-auto", action="store_true")
    next_cmd.add_argument("--reprompt-running", action="store_true")
    next_cmd.add_argument("--require-session-binding", action="store_true")
    next_cmd.add_argument("--json", action="store_true")
    add_identity_args(next_cmd)
    next_cmd.set_defaults(func=command_next)

    set_stage = sub.add_parser("set-stage", help="update a top-level stage status")
    set_stage.add_argument("stage")
    set_stage.add_argument("status", choices=["pending", "running", "completed", "error"])
    set_stage.add_argument("--run-id")
    set_stage.add_argument("--message")
    set_stage.add_argument("--evaluation-status", choices=["pending", "pass", "warn", "fail"])
    add_identity_args(set_stage)
    set_stage.set_defaults(func=command_set_stage)

    set_generate = sub.add_parser("set-generate-phase", help="update a generated phase status")
    set_generate.add_argument("phase_id")
    set_generate.add_argument("status", choices=["pending", "running", "completed", "error", "failed"])
    set_generate.add_argument("--run-id")
    set_generate.add_argument("--message")
    add_identity_args(set_generate)
    set_generate.set_defaults(func=command_set_generate_phase)

    set_commit = sub.add_parser("set-commit", help="record a commit prompt result")
    set_commit.add_argument("key")
    set_commit.add_argument("status", choices=["committed", "no_changes", "skipped", "failed"])
    set_commit.add_argument("--run-id")
    set_commit.add_argument("--message")
    add_identity_args(set_commit)
    set_commit.set_defaults(func=command_set_commit)

    wait_user = sub.add_parser("wait-user", help="pause a run for a clarify user decision")
    wait_user.add_argument("--stage", required=True)
    wait_user.add_argument("--run-id")
    wait_user.add_argument("--message", required=True)
    add_identity_args(wait_user)
    wait_user.set_defaults(func=command_wait_user)

    pause = sub.add_parser("pause", help="manually pause a run")
    pause.add_argument("--run-id")
    pause.add_argument("--message", default="manual pause")
    add_identity_args(pause)
    pause.set_defaults(func=command_pause)

    resume = sub.add_parser("resume", help="resume and rebind an active run")
    resume.add_argument("--run-id")
    resume.add_argument("--json", action="store_true")
    add_identity_args(resume)
    resume.set_defaults(func=command_resume)

    park = sub.add_parser("park-active", help="pause the active run and clear the active slot")
    park.add_argument("--message", default="manual pause before starting a new phaseharness run")
    park.add_argument("--json", action="store_true")
    park.set_defaults(func=command_park_active)

    clear = sub.add_parser("clear-active", help="deactivate the active run")
    clear.set_defaults(func=command_clear_active)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if getattr(args, "command", None) in STATE_LOCKED_COMMANDS:
            root = find_project_root()
            with state_lock(root):
                return args.func(args)
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
