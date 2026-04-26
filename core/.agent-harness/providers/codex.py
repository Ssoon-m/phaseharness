from __future__ import annotations

import shutil
import subprocess

from base import BaseProvider, ProviderResult, run_subprocess


class CodexProvider(BaseProvider):
    name = "codex"

    def __init__(self, binary: str = "codex") -> None:
        self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _exec_help(self) -> str:
        if not self.available():
            return ""
        try:
            result = subprocess.run(
                [self.binary, "exec", "--help"],
                text=True,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            return ""
        return result.stdout + result.stderr

    def _supports(self, flag: str) -> bool:
        return flag in self._exec_help()

    def run_prompt(
        self,
        prompt: str,
        *,
        cwd: str,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
        sandbox_mode: str = "workspace-write",
        approval_policy: str = "never",
        prompt_handoff: str = "stdin",
        capture_json: bool = False,
    ) -> ProviderResult:
        if not self.available():
            return {
                "exit_code": 127,
                "stdout": "",
                "stderr": f"Codex binary not found: {self.binary}",
                "failure_category": "runtime_error",
            }

        cmd = [self.binary, "exec"]
        if self._supports("--sandbox"):
            cmd.extend(["--sandbox", sandbox_mode])
        if self._supports("--ask-for-approval"):
            cmd.extend(["--ask-for-approval", approval_policy])
        if self._supports("--ignore-user-config"):
            cmd.append("--ignore-user-config")
        if self._supports("--ephemeral"):
            cmd.append("--ephemeral")

        if prompt_handoff == "arg":
            cmd.append(prompt)
            return run_subprocess(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)
        return run_subprocess(
            cmd,
            cwd=cwd,
            env=env,
            input_text=prompt,
            timeout_sec=timeout_sec,
        )
