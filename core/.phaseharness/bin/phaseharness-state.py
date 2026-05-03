#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE_ORDER = ["clarify", "context_gather", "plan", "generate", "evaluate"]
COMMIT_MODES = ["none", "final", "phase"]
ARTIFACTS = {
    "clarify": "artifacts/01-clarify.md",
    "context_gather": "artifacts/02-context.md",
    "plan": "artifacts/03-plan.md",
    "generate": "artifacts/04-generate.md",
    "evaluate": "artifacts/05-evaluate.md",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True)


def git_head(root: Path) -> str:
    result = git(root, "rev-parse", "HEAD")
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
        code = raw[:2]
        paths.add(raw[3:])
        if "R" in code or "C" in code:
            if index < len(chunks) and chunks[index]:
                paths.add(chunks[index])
                index += 1
    return sorted(paths)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "task"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def phaseharness_dir(root: Path) -> Path:
    return root / ".phaseharness"


def active_path(root: Path) -> Path:
    return phaseharness_dir(root) / "state" / "active.json"


def index_path(root: Path) -> Path:
    return phaseharness_dir(root) / "state" / "index.json"


def runs_dir(root: Path) -> Path:
    return phaseharness_dir(root) / "runs"


def next_run_id(root: Path, request: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{stamp}-{slugify(request)}"
    candidate = base
    suffix = 2
    while (runs_dir(root) / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def initial_state(
    root: Path,
    run_id: str,
    request: str,
    loop_count: int,
    max_attempts_per_phase: int,
    commit_mode: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "request": request,
        "status": "active",
        "activation_source": "phaseharness_skill",
        "current_phase": "clarify",
        "phase_order": PHASE_ORDER,
        "attempts": {
            "clarify": 0,
            "context_gather": 0,
            "plan": 0,
            "generate": 0,
            "evaluate": 0,
        },
        "loop": {
            "current": 1,
            "max": loop_count,
        },
        "max_attempts_per_phase": max_attempts_per_phase,
        "commit_mode": commit_mode,
        "commits": {},
        "generate": {
            "queue": [],
            "current_phase": None,
            "phase_attempts": {},
            "phase_status": {},
            "completed_phases": [],
            "failed_phases": [],
        },
        "needs_user": False,
        "session": {
            "provider": None,
            "session_id": None,
            "turn_id": None,
            "transcript_path": None,
            "model": None,
            "updated_at": None,
        },
        "session_history": [],
        "resume": {
            "status": "none",
            "requested_at": None,
            "summary": "",
        },
        "created_at": now_iso(),
        "git_baseline": {
            "head": git_head(root),
            "dirty_paths": git_dirty_paths(root),
        },
        "inflight": {
            "phase": None,
            "session_id": None,
            "turn_id": None,
            "started_at": None,
        },
        "phases": {
            phase: {
                "status": "pending",
                "artifact": ARTIFACTS[phase],
            }
            for phase in PHASE_ORDER
        },
        "evaluation": {
            "status": "pending",
        },
    }


def start_run(args: argparse.Namespace) -> int:
    root = find_project_root()
    active = load_json(active_path(root), {"status": "inactive", "active_run": None})
    if active.get("status") == "active" and active.get("active_run") and not args.force:
        raise RuntimeError(f"active run already exists: {active.get('active_run')}")
    run_id = args.run_id or next_run_id(root, args.request)
    run_dir = runs_dir(root) / run_id
    if run_dir.exists():
        raise RuntimeError(f"run already exists: {run_id}")
    for rel in ("artifacts", "phases", "outputs"):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    state = initial_state(root, run_id, args.request, args.loop_count, args.max_attempts_per_phase, args.commit_mode)
    save_json(run_dir / "state.json", state)
    save_json(
        active_path(root),
        {
            "schema_version": 1,
            "active_run": run_id,
            "activation_source": "phaseharness_skill",
            "status": "active",
            "session_id": None,
            "provider": None,
            "updated_at": now_iso(),
        },
    )
    index = load_json(index_path(root), {"schema_version": 1, "runs": []})
    runs = index.setdefault("runs", [])
    runs.append(
        {
            "run_id": run_id,
            "request": args.request,
            "status": "active",
            "loop_count": args.loop_count,
            "max_attempts_per_phase": args.max_attempts_per_phase,
            "commit_mode": args.commit_mode,
            "created_at": state["created_at"],
        }
    )
    save_json(index_path(root), index)
    print(run_id)
    return 0


def status_run(args: argparse.Namespace) -> int:
    root = find_project_root()
    active = load_json(active_path(root), {"status": "inactive", "active_run": None})
    if args.json:
        print(json.dumps(active, indent=2, ensure_ascii=False))
    else:
        print(active.get("active_run") or "inactive")
    return 0


def resume_run(args: argparse.Namespace) -> int:
    root = find_project_root()
    active = load_json(active_path(root), {"active_run": None, "status": "inactive"})
    run_id = args.run_id or active.get("active_run")
    if not run_id:
        raise RuntimeError("no active run to resume")
    state_file = runs_dir(root) / str(run_id) / "state.json"
    state = load_json(state_file)
    if state.get("status") == "completed":
        raise RuntimeError(f"run is already completed: {run_id}")
    if state.get("status") == "error":
        raise RuntimeError(f"run is in error state: {run_id}")
    current_phase = str(state.get("current_phase") or "clarify")
    phase_state = state.get("phases", {}).get(current_phase, {})
    if isinstance(phase_state, dict) and phase_state.get("status") == "waiting_user":
        phase_state["status"] = "pending"
        phase_state["updated_at"] = now_iso()
    state["status"] = "active"
    state["needs_user"] = False
    state["resume"] = {
        "status": "requested",
        "requested_at": now_iso(),
        "summary": args.summary or "",
    }
    save_json(state_file, state)
    save_json(
        active_path(root),
        {
            "schema_version": 1,
            "active_run": run_id,
            "activation_source": "phaseharness_skill",
            "status": "active",
            "session_id": None,
            "provider": None,
            "resume_requested_at": state["resume"]["requested_at"],
            "updated_at": now_iso(),
        },
    )
    print(run_id)
    return 0


def set_phase(args: argparse.Namespace) -> int:
    root = find_project_root()
    run_id = args.run_id or load_json(active_path(root)).get("active_run")
    if not run_id:
        raise RuntimeError("no active run")
    state_file = runs_dir(root) / str(run_id) / "state.json"
    state = load_json(state_file)
    phase = state["phases"][args.phase]
    phase["status"] = args.status
    phase["updated_at"] = now_iso()
    if args.status == "completed":
        phase["completed_at"] = now_iso()
    if args.error_message:
        phase["error_message"] = args.error_message
    if args.evaluation_status:
        state.setdefault("evaluation", {})["status"] = args.evaluation_status
        state["evaluation"]["updated_at"] = now_iso()
    state["needs_user"] = args.status == "waiting_user"
    if args.status == "waiting_user":
        state["status"] = "waiting_user"
    elif state.get("status") == "waiting_user":
        state["status"] = "active"
    save_json(state_file, state)
    return 0


def set_generate_phase(args: argparse.Namespace) -> int:
    root = find_project_root()
    run_id = args.run_id or load_json(active_path(root)).get("active_run")
    if not run_id:
        raise RuntimeError("no active run")
    state_file = runs_dir(root) / str(run_id) / "state.json"
    state = load_json(state_file)
    generate = state.setdefault(
        "generate",
        {
            "queue": [],
            "current_phase": None,
            "phase_attempts": {},
            "phase_status": {},
            "completed_phases": [],
            "failed_phases": [],
        },
    )
    queue = generate.setdefault("queue", [])
    if args.phase_id not in queue:
        queue.append(args.phase_id)
    phase_status = generate.setdefault("phase_status", {})
    phase_status[args.phase_id] = args.status
    if args.status == "completed":
        completed = generate.setdefault("completed_phases", [])
        if args.phase_id not in completed:
            completed.append(args.phase_id)
    if args.status == "error":
        failed = generate.setdefault("failed_phases", [])
        if args.phase_id not in failed:
            failed.append(args.phase_id)
    if args.error_message:
        errors = generate.setdefault("phase_errors", {})
        errors[args.phase_id] = args.error_message
    if generate.get("current_phase") is None:
        generate["current_phase"] = args.phase_id
    state["current_phase"] = "generate"
    state.setdefault("phases", {}).setdefault("generate", {})["status"] = "running"
    save_json(state_file, state)
    return 0


def clear_active(args: argparse.Namespace) -> int:
    root = find_project_root()
    save_json(
        active_path(root),
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
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage phaseharness file state.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Create and activate a phaseharness run")
    start.add_argument("--request", required=True)
    start.add_argument("--run-id", default=None)
    start.add_argument("--loop-count", type=positive_int, required=True)
    start.add_argument("--max-attempts-per-phase", type=positive_int, required=True)
    start.add_argument("--commit-mode", choices=COMMIT_MODES, required=True)
    start.add_argument("--force", action="store_true", help="Create a new run even when another run is active")
    start.set_defaults(func=start_run)

    status = sub.add_parser("status", help="Print active run status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=status_run)

    resume = sub.add_parser("resume", help="Request continuation of an active run from the current session")
    resume.add_argument("--run-id", default=None)
    resume.add_argument("--summary", default="")
    resume.set_defaults(func=resume_run)

    phase = sub.add_parser("set-phase", help="Update a phase status")
    phase.add_argument("phase", choices=PHASE_ORDER)
    phase.add_argument("status", choices=["pending", "running", "waiting_user", "completed", "error"])
    phase.add_argument("--run-id", default=None)
    phase.add_argument("--error-message", default=None)
    phase.add_argument("--evaluation-status", choices=["pending", "running", "pass", "warn", "fail"], default=None)
    phase.set_defaults(func=set_phase)

    generate_phase = sub.add_parser("set-generate-phase", help="Update a planned implementation phase status")
    generate_phase.add_argument("phase_id")
    generate_phase.add_argument("status", choices=["pending", "running", "completed", "error"])
    generate_phase.add_argument("--run-id", default=None)
    generate_phase.add_argument("--error-message", default=None)
    generate_phase.set_defaults(func=set_generate_phase)

    clear = sub.add_parser("clear-active", help="Deactivate the active run")
    clear.set_defaults(func=clear_active)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
