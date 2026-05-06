#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, input=input_text, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result


def copy_phaseharness(target: Path) -> None:
    shutil.copytree(ROOT / "core" / ".phaseharness", target / ".phaseharness", dirs_exist_ok=True)


def init_state(target: Path) -> None:
    state_dir = target / ".phaseharness" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    active = state_dir / "active.json"
    index = state_dir / "index.json"
    if not active.exists():
        active.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "active_run": None,
                    "activation_source": None,
                    "status": "inactive",
                    "session_id": None,
                    "provider": None,
                },
                indent=2,
            )
            + "\n"
        )
    if not index.exists():
        index.write_text(json.dumps({"schema_version": 1, "runs": []}, indent=2) + "\n")


def install_fixture(target: Path) -> None:
    copy_phaseharness(target)
    init_state(target)
    run(["chmod", "+x", ".phaseharness/bin/phaseharness-hook.py", ".phaseharness/bin/phaseharness-sync-bridges.py", ".phaseharness/bin/phaseharness-state.py", ".phaseharness/bin/commit-result.py", ".phaseharness/hooks/claude-stop.sh", ".phaseharness/hooks/codex-stop.sh", ".phaseharness/hooks/claude-session-start.sh", ".phaseharness/hooks/codex-session-start.sh"], target)


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
                            "hooks": [{"type": "command", "command": "echo existing-claude-hook"}],
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
                            "hooks": [{"type": "command", "command": "echo existing-codex-hook"}],
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
    if "SessionStart" not in claude.get("hooks", {}) or "Stop" not in claude.get("hooks", {}):
        raise SystemExit("Claude SessionStart and Stop hooks were not installed")
    if "SessionStart" not in codex.get("hooks", {}) or "Stop" not in codex.get("hooks", {}):
        raise SystemExit("Codex SessionStart and Stop hooks were not installed")
    if "startup|resume|clear|compact" not in claude_text:
        raise SystemExit("Claude SessionStart matcher was not installed")
    if "startup|resume|clear" not in codex_text:
        raise SystemExit("Codex SessionStart matcher was not installed")
    if "git -C" not in claude_text or "rev-parse --show-toplevel" not in claude_text:
        raise SystemExit("Claude hook command should be bounded to the repository root")
    if "while [" in claude_text or "dirname" in claude_text:
        raise SystemExit("Claude hook command should not search past the repository root")
    if claude_text.count(".phaseharness") != 2:
        raise SystemExit("Claude phaseharness hook was not installed idempotently")
    if codex_text.count(".phaseharness") != 2:
        raise SystemExit("Codex phaseharness hook was not installed idempotently")
    permissions = claude.get("permissions", {})
    if permissions.get("defaultMode") != "bypassPermissions":
        raise SystemExit("Claude bypass permissions mode was not enabled")
    if "Agent(phaseharness-generate)" not in permissions.get("allow", []):
        raise SystemExit("Claude phaseharness subagent permission was not allowed")
    config = (target / ".codex" / "config.toml").read_text()
    if "codex_hooks = true" not in config:
        raise SystemExit("Codex hooks feature flag was not enabled")
    if config.count("# BEGIN phaseharness managed permissions") != 1:
        raise SystemExit("Codex phaseharness permission block was not installed once")
    if 'approval_policy = "never"' not in config or 'sandbox_mode = "danger-full-access"' not in config:
        raise SystemExit("Codex full approval/sandbox permissions were not enabled")
    if "sandbox_workspace_write.network_access = true" not in config or 'sandbox_workspace_write.writable_roots = ["."]' not in config:
        raise SystemExit("Codex workspace-write sandbox settings were not generated")
    if "# BEGIN phaseharness managed hook" in config or "codex-stop.sh" in config:
        raise SystemExit("Codex phaseharness hooks should only be installed in hooks.json")


def assert_codex_hooks_json_replaces_managed_inline_hooks(tmp: Path) -> None:
    target = tmp / "codex-hooks-json"
    target.mkdir()
    run(["git", "init", "--initial-branch=main"], target)
    run(["git", "-c", "user.name=Harness Smoke", "-c", "user.email=smoke@example.invalid", "commit", "--allow-empty", "-m", "test: initial"], target)
    install_fixture(target)
    (target / ".codex").mkdir(exist_ok=True)
    (target / ".codex" / "config.toml").write_text(
        "[features]\ncodex_hooks = false\n\n"
        "[[hooks.PostToolUse]]\n"
        "matcher = \"Bash\"\n"
        "[[hooks.PostToolUse.hooks]]\n"
        "type = \"command\"\n"
        "command = \"echo existing-inline-codex-hook\"\n"
        "\n"
        "# BEGIN phaseharness managed hook\n"
        "[[hooks.SessionStart]]\n"
        "matcher = \"startup|resume|clear\"\n"
        "[[hooks.SessionStart.hooks]]\n"
        "type = \"command\"\n"
        "command = \"sh .phaseharness/hooks/codex-session-start.sh\"\n"
        "\n"
        "[[hooks.Stop]]\n"
        "[[hooks.Stop.hooks]]\n"
        "type = \"command\"\n"
        "command = \"sh .phaseharness/hooks/codex-stop.sh\"\n"
        "# END phaseharness managed hook\n"
    )
    run(["python3", ".phaseharness/bin/phaseharness-sync-bridges.py", "--runtime", "codex"], target)
    run(["python3", ".phaseharness/bin/phaseharness-sync-bridges.py", "--runtime", "codex"], target)
    config = (target / ".codex" / "config.toml").read_text()
    if "existing-inline-codex-hook" not in config:
        raise SystemExit("existing inline Codex hook was not preserved")
    if "codex_hooks = true" not in config:
        raise SystemExit("Codex hooks feature flag was not enabled")
    if config.count("# BEGIN phaseharness managed permissions") != 1:
        raise SystemExit("Codex phaseharness permission block was not installed once")
    if 'approval_policy = "never"' not in config or 'sandbox_mode = "danger-full-access"' not in config:
        raise SystemExit("Codex full approval/sandbox permissions were not enabled")
    if "sandbox_workspace_write.network_access = true" not in config or 'sandbox_workspace_write.writable_roots = ["."]' not in config:
        raise SystemExit("Codex workspace-write sandbox settings were not generated")
    if "# BEGIN phaseharness managed hook" in config:
        raise SystemExit("old inline Codex phaseharness hook block was not removed")
    if "codex-session-start.sh" in config or "codex-stop.sh" in config:
        raise SystemExit("Codex phaseharness hooks should not be written to config.toml")
    codex = json.loads((target / ".codex" / "hooks.json").read_text())
    codex_text = json.dumps(codex)
    if "SessionStart" not in codex.get("hooks", {}) or "Stop" not in codex.get("hooks", {}):
        raise SystemExit("Codex hooks.json SessionStart and Stop hooks were not installed")
    if codex_text.count(".phaseharness") != 2:
        raise SystemExit("Codex hooks.json phaseharness hook was not installed idempotently")


def assert_permission_config_is_ssot(tmp: Path) -> None:
    target = tmp / "permission-config"
    target.mkdir()
    run(["git", "init", "--initial-branch=main"], target)
    run(["git", "-c", "user.name=Harness Smoke", "-c", "user.email=smoke@example.invalid", "commit", "--allow-empty", "-m", "test: initial"], target)
    install_fixture(target)

    config_path = target / ".phaseharness" / "config.toml"
    config = config_path.read_text()
    config = config.replace('defaultMode = "bypassPermissions"', 'defaultMode = "acceptEdits"')
    config = config.replace('permissionMode = "bypassPermissions"', 'permissionMode = "acceptEdits"')
    config = config.replace("allowManagedSubagents = true", "allowManagedSubagents = false")
    config = config.replace('approval_policy = "never"', 'approval_policy = "on-request"')
    config = config.replace('sandbox_mode = "danger-full-access"', 'sandbox_mode = "workspace-write"')
    config = config.replace("network_access = true", "network_access = false")
    config = config.replace('writable_roots = ["."]', 'writable_roots = [".", "../shared"]')
    config_path.write_text(config)

    run(["python3", ".phaseharness/bin/phaseharness-sync-bridges.py"], target)
    claude = json.loads((target / ".claude" / "settings.json").read_text())
    if claude.get("permissions", {}).get("defaultMode") != "acceptEdits":
        raise SystemExit("Claude permissions were not generated from .phaseharness/config.toml")
    if "Agent(phaseharness-generate)" in claude.get("permissions", {}).get("allow", []):
        raise SystemExit("Claude managed subagent allow rules ignored .phaseharness/config.toml")

    codex_config = (target / ".codex" / "config.toml").read_text()
    if 'approval_policy = "on-request"' not in codex_config or 'sandbox_mode = "workspace-write"' not in codex_config:
        raise SystemExit("Codex permissions were not generated from .phaseharness/config.toml")
    if "sandbox_workspace_write.network_access = false" not in codex_config or 'sandbox_workspace_write.writable_roots = [".", "../shared"]' not in codex_config:
        raise SystemExit("Codex sandbox_workspace_write settings were not generated from .phaseharness/config.toml")
    if "permissionMode: acceptEdits" not in (target / ".claude" / "agents" / "phaseharness-generate.md").read_text():
        raise SystemExit("Claude subagent permissions were not generated from .phaseharness/config.toml")
    codex_agent = (target / ".codex" / "agents" / "phaseharness-generate.toml").read_text()
    if 'approval_policy = "on-request"' not in codex_agent or 'sandbox_mode = "workspace-write"' not in codex_agent:
        raise SystemExit("Codex subagent permissions were not generated from .phaseharness/config.toml")
    if "sandbox_workspace_write.network_access = false" not in codex_agent or 'sandbox_workspace_write.writable_roots = [".", "../shared"]' not in codex_agent:
        raise SystemExit("Codex subagent sandbox settings were not generated from .phaseharness/config.toml")


def assert_no_legacy_paths(target: Path) -> None:
    for rel in (
        "scripts",
        "tasks",
    ):
        if (target / rel).exists():
            raise SystemExit(f"legacy path should not be installed: {rel}")


def assert_native_subagents(target: Path) -> None:
    claude_agents = target / ".claude" / "agents"
    codex_agents = target / ".codex" / "agents"
    for name in ("clarify", "context-gather", "plan", "generate", "evaluate"):
        claude_path = claude_agents / f"phaseharness-{name}.md"
        codex_path = codex_agents / f"phaseharness-{name}.toml"
        if not claude_path.exists():
            raise SystemExit(f"missing Claude native subagent: {claude_path.relative_to(target)}")
        if not codex_path.exists():
            raise SystemExit(f"missing Codex native subagent: {codex_path.relative_to(target)}")
        claude_text = claude_path.read_text()
        codex_text = codex_path.read_text()
        if f"name: phaseharness-{name}" not in claude_text or "description:" not in claude_text:
            raise SystemExit(f"invalid Claude subagent frontmatter: {claude_path.relative_to(target)}")
        if "developer_instructions" not in codex_text or "name = " not in codex_text:
            raise SystemExit(f"invalid Codex subagent TOML: {codex_path.relative_to(target)}")
        if "Use proactively" not in claude_text or "Use proactively" not in codex_text:
            raise SystemExit(f"subagent description should encourage delegation: {claude_path.relative_to(target)}")
        if "permissionMode: bypassPermissions" not in claude_text:
            raise SystemExit(f"Claude subagent permissions should bypass prompts: {claude_path.relative_to(target)}")
        if 'approval_policy = "never"' not in codex_text or 'sandbox_mode = "danger-full-access"' not in codex_text:
            raise SystemExit(f"Codex subagent permissions should bypass prompts: {codex_path.relative_to(target)}")
        if "sandbox_workspace_write.network_access = true" not in codex_text or 'sandbox_workspace_write.writable_roots = ["."]' not in codex_text:
            raise SystemExit(f"Codex subagent sandbox settings should be generated: {codex_path.relative_to(target)}")
    if "phaseharness_generate" not in (codex_agents / "phaseharness-generate.toml").read_text():
        raise SystemExit("Codex generate subagent name was not written")


def assert_skill_starts_with_hooked_clarify(target: Path) -> None:
    text = (target / ".phaseharness" / "skills" / "phaseharness" / "SKILL.md").read_text()
    if "Do not perform `clarify` in the current conversation." not in text:
        raise SystemExit("phaseharness skill should leave clarify to the Stop hook")
    if "Stop` hook will read the active run and continue" not in text or "with `clarify` through" not in text:
        raise SystemExit("phaseharness skill should document hooked clarify startup")


def hook_input(target: Path, session_id: str, turn_id: str) -> str:
    return json.dumps(
        {
            "cwd": str(target),
            "hook_event_name": "Stop",
            "session_id": session_id,
            "turn_id": turn_id,
            "transcript_path": str(target / ".tmp-transcript.jsonl"),
            "model": "test-model",
            "stop_hook_active": False,
            "last_assistant_message": "done",
        }
    )


def session_start_input(target: Path, session_id: str = "session-start", source: str = "startup") -> str:
    return json.dumps(
        {
            "cwd": str(target),
            "hook_event_name": "SessionStart",
            "session_id": session_id,
            "source": source,
            "transcript_path": str(target / ".tmp-transcript.jsonl"),
            "model": "test-model",
        }
    )


def assert_hook_noop(target: Path) -> None:
    claude = run(["sh", ".phaseharness/hooks/claude-stop.sh"], target, hook_input(target, "s0", "t0"))
    if claude.stdout.strip():
        raise SystemExit(f"Claude no-op should be empty, got: {claude.stdout!r}")
    codex = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "s0", "t0"))
    if json.loads(codex.stdout).get("continue") is not True:
        raise SystemExit("Codex no-op should return continue true")


def assert_session_start_syncs_bridges(target: Path) -> None:
    clarify_source = target / ".phaseharness" / "subagents" / "clarify.md"
    clarify_source.write_text(clarify_source.read_text() + "\nSessionStart Claude sync marker.\n")
    claude = run(["sh", ".phaseharness/hooks/claude-session-start.sh"], target, session_start_input(target, "claude-session"))
    if claude.stdout.strip():
        raise SystemExit("Claude SessionStart sync should not write stdout context")
    if "SessionStart Claude sync marker." not in (target / ".claude" / "agents" / "phaseharness-clarify.md").read_text():
        raise SystemExit("Claude SessionStart did not resync subagent bridge from .phaseharness")

    clarify_source.write_text(clarify_source.read_text() + "\nSessionStart Codex sync marker.\n")
    codex = run(["sh", ".phaseharness/hooks/codex-session-start.sh"], target, session_start_input(target, "codex-session"))
    if codex.stdout.strip():
        raise SystemExit("Codex SessionStart sync should not write stdout context")
    if "SessionStart Codex sync marker." not in (target / ".codex" / "agents" / "phaseharness-clarify.toml").read_text():
        raise SystemExit("Codex SessionStart did not resync subagent bridge from .phaseharness")
    assert_hook_merge(target)


def assert_start_requires_choices(target: Path) -> None:
    missing = subprocess.run(
        ["python3", ".phaseharness/bin/phaseharness-state.py", "start", "--request", "missing choices"],
        cwd=str(target),
        text=True,
        capture_output=True,
    )
    if missing.returncode == 0:
        raise SystemExit("start should require explicit loop count, max attempts per phase, and commit mode")


def assert_new_run_starts_before_clarify(target: Path) -> None:
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"], target)
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "verify hooked clarify startup",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "2",
            "--commit-mode",
            "none",
        ],
        target,
    )
    run_id = result.stdout.strip()
    state = json.loads((target / ".phaseharness" / "runs" / run_id / "state.json").read_text())
    if state.get("attempts", {}).get("clarify") != 0:
        raise SystemExit("new runs should not pre-consume a clarify attempt")
    if state.get("phases", {}).get("clarify", {}).get("status") != "pending":
        raise SystemExit("new runs should leave clarify pending for the Stop hook")
    if state.get("inflight", {}).get("phase") is not None:
        raise SystemExit("new runs should not mark clarify inflight before the Stop hook")
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"], target)


def assert_hook_activation_and_resume(target: Path) -> None:
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "add a small fixture",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "3",
            "--commit-mode",
            "none",
        ],
        target,
    )
    run_id = result.stdout.strip()
    run_dir = target / ".phaseharness" / "runs" / run_id
    (run_dir / "artifacts" / "01-clarify.md").write_text("# Phase 1: Clarify\n\nDone when fixture exists.\n")
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "set-phase", "clarify", "completed"], target)

    first = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "s1", "t1"))
    first_json = json.loads(first.stdout)
    if first_json.get("decision") != "block" or "context_gather" not in first_json.get("reason", ""):
        raise SystemExit("active run did not continue to context_gather")
    if "Do not execute this phase in the parent conversation." not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt should prohibit parent phase execution")
    if "Loop: `1` of `2`" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not include loop count")
    if "Attempt: `1` of `3`" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not include max attempts per phase")
    if "Commit mode: `none`" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not include commit mode")
    if "Codex: directly spawn exactly one custom agent named `phaseharness_context_gather`" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not request the Codex subagent")
    if "Claude Code: directly invoke the `phaseharness-context-gather` subagent" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not request the Claude subagent")
    if "subagent_unavailable" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not define subagent unavailable handling")
    if "Codex must call `close_agent`" not in first_json.get("reason", ""):
        raise SystemExit("continuation prompt did not require Codex subagent cleanup")

    other_session = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "s2", "t2"))
    if json.loads(other_session.stdout).get("continue") is not True:
        raise SystemExit("different session should not auto-resume without skill resume")

    run(["python3", ".phaseharness/bin/phaseharness-state.py", "resume", "--summary", "resume in new session"], target)
    resumed = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "s2", "t3"))
    resumed_json = json.loads(resumed.stdout)
    if resumed_json.get("decision") != "block":
        raise SystemExit("resume request did not produce continuation")
    state = json.loads((run_dir / "state.json").read_text())
    if state.get("session", {}).get("session_id") != "s2":
        raise SystemExit("resume did not bind the new session")
    if not state.get("session_history"):
        raise SystemExit("previous session was not recorded in session_history")


def continue_hook(target: Path, session_id: str, turn_id: str) -> str:
    result = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, session_id, turn_id))
    data = json.loads(result.stdout)
    if data.get("decision") != "block":
        raise SystemExit(f"expected continuation for {turn_id}, got: {data}")
    return data.get("reason", "")


def complete_phase(target: Path, run_id: str, phase: str, artifact: str, text: str, turn_id: str) -> str:
    run_dir = target / ".phaseharness" / "runs" / run_id
    (run_dir / artifact).write_text(text)
    args = ["python3", ".phaseharness/bin/phaseharness-state.py", "set-phase", phase, "completed"]
    if phase == "evaluate":
        args.extend(["--evaluation-status", "pass"])
    run(args, target)
    result = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "workflow-session", turn_id))
    data = json.loads(result.stdout)
    if phase == "evaluate":
        if data.get("continue") is True:
            return ""
        if data.get("decision") == "block":
            return data.get("reason", "")
        else:
            raise SystemExit(f"evaluate completion should deactivate hook, got: {data}")
    if data.get("decision") != "block":
        raise SystemExit(f"expected continuation after {phase}, got: {data}")
    return data.get("reason", "")


def write_implementation_phase(target: Path, run_id: str, phase_id: str, text: str | None = None) -> None:
    run_dir = target / ".phaseharness" / "runs" / run_id
    phase_file = run_dir / "phases" / f"{phase_id}.md"
    phase_file.write_text(text or f"# {phase_id}\n\n## Work\n- test implementation phase\n")


def complete_generate_phase(target: Path, run_id: str, phase_id: str, text: str, turn_id: str) -> str:
    run_dir = target / ".phaseharness" / "runs" / run_id
    artifact = run_dir / "artifacts" / "04-generate.md"
    existing = artifact.read_text() if artifact.exists() else ""
    artifact.write_text(existing + text)
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "set-generate-phase", phase_id, "completed"], target)
    result = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "workflow-session", turn_id))
    data = json.loads(result.stdout)
    if data.get("decision") != "block":
        raise SystemExit(f"expected continuation after implementation phase {phase_id}, got: {data}")
    return data.get("reason", "")


def run_phaseharness_commit(target: Path, run_id: str, key: str, mode: str, implementation_phase: str | None = None) -> None:
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
    run(command, target)


def assert_full_workflow(target: Path) -> None:
    run(
        ["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"],
        target,
    )
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "run full workflow",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "3",
            "--commit-mode",
            "none",
        ],
        target,
    )
    run_id = result.stdout.strip()
    run_dir = target / ".phaseharness" / "runs" / run_id

    # A partial artifact without completed state must not advance the phase.
    (run_dir / "artifacts" / "01-clarify.md").write_text("# Phase 1\n")
    first = continue_hook(target, "workflow-session", "wf-1")
    if "clarify" not in first:
        raise SystemExit("running clarify should continue clarify until state marks it completed")
    if "Codex: directly spawn exactly one custom agent named `phaseharness_clarify`" not in first:
        raise SystemExit("clarify prompt did not request the Codex clarify subagent")

    prompt = complete_phase(target, run_id, "clarify", "artifacts/01-clarify.md", "# Phase 1\nDone\n", "wf-2")
    if "context_gather" not in prompt:
        raise SystemExit("clarify did not advance to context_gather")
    prompt = complete_phase(target, run_id, "context_gather", "artifacts/02-context.md", "# Phase 2\nDone\n", "wf-3")
    if "plan" not in prompt:
        raise SystemExit("context_gather did not advance to plan")
    write_implementation_phase(target, run_id, "phase-001")
    prompt = complete_phase(target, run_id, "plan", "artifacts/03-plan.md", "# Phase 3\nDone\n", "wf-4")
    if "generate" not in prompt:
        raise SystemExit("plan did not advance to generate")
    if "phase-001" not in prompt:
        raise SystemExit("generate prompt did not target phase-001")
    prompt = complete_generate_phase(target, run_id, "phase-001", "# Phase 4\nDone\n", "wf-5")
    if "evaluate" not in prompt:
        raise SystemExit("generate did not advance to evaluate")
    complete_phase(target, run_id, "evaluate", "artifacts/05-evaluate.md", "# Phase 5\n\n## Result\npass\n", "wf-6")

    state = json.loads((run_dir / "state.json").read_text())
    if state.get("status") != "completed":
        raise SystemExit("full workflow did not mark run completed")
    active = json.loads((target / ".phaseharness" / "state" / "active.json").read_text())
    if active.get("status") != "inactive" or active.get("active_run") is not None:
        raise SystemExit("full workflow did not clear active run")


def assert_same_turn_id_advances_between_phases(target: Path) -> None:
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"], target)
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "same turn id workflow",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "2",
            "--commit-mode",
            "none",
        ],
        target,
    )
    run_id = result.stdout.strip()
    run_dir = target / ".phaseharness" / "runs" / run_id
    session_id = "same-turn-session"
    turn_id = "same-turn"

    prompt = continue_hook(target, session_id, turn_id)
    if "clarify" not in prompt:
        raise SystemExit("same turn workflow did not start clarify")

    (run_dir / "artifacts" / "01-clarify.md").write_text("# Clarify\nDone\n")
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "set-phase", "clarify", "completed"], target)
    prompt = continue_hook(target, session_id, turn_id)
    if "context_gather" not in prompt:
        raise SystemExit("same turn workflow did not advance to context_gather")

    (run_dir / "artifacts" / "02-context.md").write_text("# Context\nDone\n")
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "set-phase", "context_gather", "completed"], target)
    prompt = continue_hook(target, session_id, turn_id)
    if "plan" not in prompt:
        raise SystemExit("same turn workflow did not advance to plan")


def assert_evaluate_failure_loops(target: Path) -> None:
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"], target)
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "exercise evaluate loop",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "2",
            "--commit-mode",
            "none",
        ],
        target,
    )
    run_id = result.stdout.strip()
    run_dir = target / ".phaseharness" / "runs" / run_id
    continue_hook(target, "workflow-session", "loop-1")
    complete_phase(target, run_id, "clarify", "artifacts/01-clarify.md", "# Clarify\nDone\n", "loop-2")
    complete_phase(target, run_id, "context_gather", "artifacts/02-context.md", "# Context\nDone\n", "loop-3")
    write_implementation_phase(target, run_id, "phase-001")
    complete_phase(target, run_id, "plan", "artifacts/03-plan.md", "# Plan\nDone\n", "loop-4")
    complete_generate_phase(target, run_id, "phase-001", "# Generate\nphase-001 done\n", "loop-5")

    write_implementation_phase(target, run_id, "phase-002", "# phase-002\n\nFollow-up from evaluate.\n")
    (run_dir / "artifacts" / "05-evaluate.md").write_text("# Evaluate\n\n## Result\nfail\n")
    run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "set-phase",
            "evaluate",
            "completed",
            "--evaluation-status",
            "fail",
        ],
        target,
    )
    follow_up = continue_hook(target, "workflow-session", "loop-6")
    if "Loop: `2` of `2`" not in follow_up or "phase-002" not in follow_up:
        raise SystemExit("evaluate fail did not loop back to follow-up implementation phase")
    complete_generate_phase(target, run_id, "phase-002", "# Generate\nphase-002 done\n", "loop-7")
    complete_phase(target, run_id, "evaluate", "artifacts/05-evaluate.md", "# Evaluate\n\n## Result\npass\n", "loop-8")

    state = json.loads((run_dir / "state.json").read_text())
    if state.get("status") != "completed" or state.get("loop", {}).get("current") != 2:
        raise SystemExit("evaluate loop did not complete on second loop")


def assert_waiting_user_resume(target: Path) -> None:
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "needs user input",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "2",
            "--commit-mode",
            "none",
        ],
        target,
    )
    run_id = result.stdout.strip()
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "set-phase", "clarify", "waiting_user"], target)
    waiting = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "waiting-session", "wait-1"))
    if json.loads(waiting.stdout).get("continue") is not True:
        raise SystemExit("waiting_user run should not auto-continue")
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "resume", "--summary", "user answered"], target)
    resumed = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "waiting-session", "wait-2"))
    data = json.loads(resumed.stdout)
    if data.get("decision") != "block" or "clarify" not in data.get("reason", ""):
        raise SystemExit("waiting_user resume did not continue clarify")
    state = json.loads((target / ".phaseharness" / "runs" / run_id / "state.json").read_text())
    if state.get("phases", {}).get("clarify", {}).get("status") != "running":
        raise SystemExit("waiting_user resume did not reset phase to running")


def assert_commit_modes(target: Path) -> None:
    run(["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"], target)
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "add phase commit file",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "2",
            "--commit-mode",
            "phase",
        ],
        target,
    )
    phase_run_id = result.stdout.strip()
    phase_run_dir = target / ".phaseharness" / "runs" / phase_run_id
    continue_hook(target, "workflow-session", "phase-1")
    complete_phase(target, phase_run_id, "clarify", "artifacts/01-clarify.md", "# Clarify\nDone\n", "phase-2")
    complete_phase(target, phase_run_id, "context_gather", "artifacts/02-context.md", "# Context\nDone\n", "phase-3")
    write_implementation_phase(target, phase_run_id, "phase-001")
    complete_phase(target, phase_run_id, "plan", "artifacts/03-plan.md", "# Plan\nDone\n", "phase-4")
    (target / "phase-product.txt").write_text("phase product\n")
    prompt = complete_generate_phase(target, phase_run_id, "phase-001", "# Generate\nDone\n", "phase-5")
    if "commit` skill" not in prompt or "--record-state-key implementation_phase-001" not in prompt:
        raise SystemExit("phase commit mode did not request the commit skill")
    run_phaseharness_commit(target, phase_run_id, "implementation_phase-001", "implementation-phase", "phase-001")
    prompt = continue_hook(target, "workflow-session", "phase-6")
    if "evaluate" not in prompt:
        raise SystemExit("phase commit mode did not advance to evaluate")
    phase_state = json.loads((phase_run_dir / "state.json").read_text())
    if phase_state.get("commits", {}).get("implementation_phase-001", {}).get("status") != "completed":
        raise SystemExit("phase commit mode did not record a completed implementation phase commit")
    tree = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], target).stdout
    if "phase-product.txt" not in tree:
        raise SystemExit("phase commit mode did not commit product file")

    run(["python3", ".phaseharness/bin/phaseharness-state.py", "clear-active"], target)
    result = run(
        [
            "python3",
            ".phaseharness/bin/phaseharness-state.py",
            "start",
            "--request",
            "add final commit file",
            "--loop-count",
            "2",
            "--max-attempts-per-phase",
            "2",
            "--commit-mode",
            "final",
        ],
        target,
    )
    final_run_id = result.stdout.strip()
    final_run_dir = target / ".phaseharness" / "runs" / final_run_id
    continue_hook(target, "workflow-session", "final-1")
    complete_phase(target, final_run_id, "clarify", "artifacts/01-clarify.md", "# Clarify\nDone\n", "final-2")
    complete_phase(target, final_run_id, "context_gather", "artifacts/02-context.md", "# Context\nDone\n", "final-3")
    write_implementation_phase(target, final_run_id, "phase-001")
    complete_phase(target, final_run_id, "plan", "artifacts/03-plan.md", "# Plan\nDone\n", "final-4")
    (target / "final-product.txt").write_text("final product\n")
    complete_generate_phase(target, final_run_id, "phase-001", "# Generate\nDone\n", "final-5")
    prompt = complete_phase(target, final_run_id, "evaluate", "artifacts/05-evaluate.md", "# Evaluate\n\n## Result\npass\n", "final-6")
    if "commit` skill" not in prompt or "--record-state-key final" not in prompt:
        raise SystemExit("final commit mode did not request the commit skill")
    run_phaseharness_commit(target, final_run_id, "final", "completed")
    result = run(["sh", ".phaseharness/hooks/codex-stop.sh"], target, hook_input(target, "workflow-session", "final-7"))
    if json.loads(result.stdout).get("continue") is not True:
        raise SystemExit("final commit mode did not deactivate after commit skill completed")
    final_state = json.loads((final_run_dir / "state.json").read_text())
    if final_state.get("commits", {}).get("final", {}).get("status") != "completed":
        raise SystemExit("final commit mode did not record a completed final commit")
    tree = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], target).stdout
    if "final-product.txt" not in tree:
        raise SystemExit("final commit mode did not commit product file")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="phaseharness-smoke-") as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "target"
        target.mkdir()
        run(["git", "init", "--initial-branch=main"], target)
        run(["git", "config", "user.name", "Harness Smoke"], target)
        run(["git", "config", "user.email", "smoke@example.invalid"], target)
        run(["git", "commit", "--allow-empty", "-m", "test: initial fixture"], target)

        install_fixture(target)
        write_existing_hooks(target)
        assert_codex_hooks_json_replaces_managed_inline_hooks(tmp_path)
        assert_permission_config_is_ssot(tmp_path)

        run(["python3", ".phaseharness/bin/phaseharness-sync-bridges.py"], target)
        run(["python3", ".phaseharness/bin/phaseharness-sync-bridges.py"], target)
        assert_hook_merge(target)
        assert_no_legacy_paths(target)
        assert_native_subagents(target)
        assert_skill_starts_with_hooked_clarify(target)

        expected = [
            ".phaseharness/bin/phaseharness-hook.py",
            ".phaseharness/bin/phaseharness-sync-bridges.py",
            ".phaseharness/bin/phaseharness-state.py",
            ".phaseharness/bin/commit-result.py",
            ".phaseharness/hooks/claude-stop.sh",
            ".phaseharness/hooks/codex-stop.sh",
            ".phaseharness/hooks/claude-session-start.sh",
            ".phaseharness/hooks/codex-session-start.sh",
            ".phaseharness/skills/phaseharness/SKILL.md",
            ".phaseharness/skills/commit/SKILL.md",
            ".claude/skills/phaseharness",
            ".claude/skills/commit",
            ".agents/skills/phaseharness",
            ".agents/skills/commit",
            ".claude/agents/phaseharness-clarify.md",
            ".codex/agents/phaseharness-clarify.toml",
        ]
        for rel in expected:
            if not (target / rel).exists():
                raise SystemExit(f"missing installed path: {rel}")

        assert_hook_noop(target)
        assert_session_start_syncs_bridges(target)
        assert_start_requires_choices(target)
        assert_new_run_starts_before_clarify(target)
        assert_hook_activation_and_resume(target)
        assert_same_turn_id_advances_between_phases(target)
        assert_full_workflow(target)
        assert_evaluate_failure_loops(target)
        assert_waiting_user_resume(target)
        assert_commit_modes(target)

        run(["python3", ".phaseharness/bin/phaseharness-state.py", "--help"], target)
        run(["python3", ".phaseharness/bin/phaseharness-hook.py", "--help"], target)
        run(["python3", ".phaseharness/bin/phaseharness-sync-bridges.py", "--help"], target)
        run(["python3", ".phaseharness/bin/commit-result.py", "--help"], target)
        run(["python3", "-m", "py_compile", ".phaseharness/bin/phaseharness-state.py", ".phaseharness/bin/phaseharness-hook.py", ".phaseharness/bin/phaseharness-sync-bridges.py", ".phaseharness/bin/commit-result.py"], target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
