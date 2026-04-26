from __future__ import annotations

import shutil
import subprocess

from base import BaseProvider, ProviderResult, run_subprocess


class ClaudeProvider(BaseProvider):
    name = "claude"

    def __init__(self, binary: str = "claude") -> None:
        self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _supports_output_json(self) -> bool:
        if not self.available():
            return False
        try:
            result = subprocess.run(
                [self.binary, "--help"],
                text=True,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            return False
        return "--output-format" in result.stdout or "--output-format" in result.stderr

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
                "stderr": f"Claude binary not found: {self.binary}",
                "failure_category": "runtime_error",
            }

        cmd = [self.binary, "-p", "--dangerously-skip-permissions"]
        if capture_json and self._supports_output_json():
            cmd.extend(["--output-format", "json"])
        cmd.append(prompt)
        return run_subprocess(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)
