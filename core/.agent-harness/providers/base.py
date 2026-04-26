from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol, TypedDict


class ProviderResult(TypedDict):
    exit_code: int
    stdout: str
    stderr: str
    failure_category: str | None


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

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
    ) -> ProviderResult: ...

    def run_role(
        self,
        role_name: str,
        role_prompt: str,
        role_input: str,
        *,
        cwd: str,
        output_schema: dict[str, Any] | None = None,
        output_path: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
        sandbox_mode: str = "read-only",
        approval_policy: str = "never",
    ) -> ProviderResult: ...


def headless_env(env: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    merged["AGENT_HEADLESS"] = "1"
    return merged


def classify_failure(exit_code: int, stderr: str) -> str | None:
    if exit_code == 0:
        return None
    text = stderr.lower()
    if "permission" in text or "sandbox" in text or "operation not permitted" in text:
        return "sandbox_blocked"
    if "context_insufficient" in text:
        return "context_insufficient"
    if "validation" in text or "acceptance criteria" in text:
        return "validation_failed"
    return "runtime_error"


def run_subprocess(
    cmd: list[str],
    *,
    cwd: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout_sec: int = 600,
) -> ProviderResult:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=headless_env(env),
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "failure_category": classify_failure(result.returncode, result.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr + f"\nTimed out after {timeout_sec}s",
            "failure_category": "runtime_error",
        }


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class BaseProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def run_role(
        self,
        role_name: str,
        role_prompt: str,
        role_input: str,
        *,
        cwd: str,
        output_schema: dict[str, Any] | None = None,
        output_path: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
        sandbox_mode: str = "read-only",
        approval_policy: str = "never",
    ) -> ProviderResult:
        schema_text = json.dumps(output_schema or {}, indent=2)
        prompt = f"""{role_prompt}

## Role Input

{role_input}

## Output Contract

Return only a JSON object. Do not wrap it in Markdown.

Expected schema hint:

```json
{schema_text}
```
"""
        result = self.run_prompt(
            prompt,
            cwd=cwd,
            env=env,
            timeout_sec=timeout_sec,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            prompt_handoff="stdin",
            capture_json=True,
        )
        data = extract_json_object(result["stdout"])
        if data is None:
            data = {
                "role": role_name,
                "decision": "reject",
                "reasons": ["Role did not return valid JSON."],
                "required_changes": [],
                "human_intervention_required": False,
            }
            if result["failure_category"]:
                data["failure_category"] = result["failure_category"]
        if output_path:
            path = Path(cwd) / output_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return result
