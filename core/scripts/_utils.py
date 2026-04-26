from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".agent-harness").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    raise RuntimeError("Could not find project root")


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


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if tomllib is not None:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        return data if isinstance(data, dict) else {}
    return _load_simple_toml(path)


def _parse_toml_value(raw: str) -> Any:
    value = raw.strip()
    if value in ("true", "false"):
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value.isdigit():
        return int(value)
    return value


def _load_simple_toml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current: dict[str, Any] = data
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = data
            for part in stripped[1:-1].split("."):
                current = current.setdefault(part, {})
            continue
        if "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        current[key.strip()] = _parse_toml_value(raw_value)
    return data


def load_config(root: Path | None = None) -> dict[str, Any]:
    root = root or find_project_root()
    return load_toml(root / ".agent-harness" / "config.toml")


def git(
    *args: str,
    root: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    root = root or find_project_root()
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def git_head(root: Path | None = None) -> str:
    result = git("rev-parse", "HEAD", root=root, check=True)
    return result.stdout.strip()


def load_provider(name: str | None = None, root: Path | None = None):
    root = root or find_project_root()
    providers_dir = root / ".agent-harness" / "providers"
    sys.path.insert(0, str(providers_dir))
    try:
        registry = importlib.import_module("registry")
        return registry.get_provider(name, load_config(root))
    finally:
        try:
            sys.path.remove(str(providers_dir))
        except ValueError:
            pass


def read_text_if_exists(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def ensure_base_state(root: Path | None = None) -> None:
    root = root or find_project_root()
    (root / "tasks").mkdir(exist_ok=True)
    index_path = root / "tasks" / "index.json"
    if not index_path.exists():
        save_json(index_path, {"tasks": []})
