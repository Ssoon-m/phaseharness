#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


MANIFEST_PATH = Path(".phaseharness") / "manifest.json"
PROTECTED_PREFIXES = (
    ".phaseharness/runs/",
    ".phaseharness/state/",
    ".phaseharness/prompts/.generated/",
)
PROTECTED_FILES = {
    ".phaseharness/context.json",
    ".phaseharness/settings.json",
    str(MANIFEST_PATH),
}


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / MANIFEST_PATH).is_file() or (current / ".git").exists():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "version": "0.1.1", "revision": "local", "managed_files": {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(f"manifest must be a JSON object: {path}")
    return data


def is_managed_path(rel: str) -> bool:
    if rel in PROTECTED_FILES:
        return False
    if any(rel.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return False
    path = Path(rel)
    if ".git" in path.parts or "__pycache__" in path.parts:
        return False
    return rel.startswith(".phaseharness/")


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def working_tree_files(root: Path) -> dict[str, str]:
    managed: dict[str, str] = {}
    for path in sorted((root / ".phaseharness").rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if is_managed_path(rel):
            managed[rel] = sha256_bytes(path.read_bytes())
    return managed


def run_git(root: Path, args: list[str], *, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} failed")
    return result.stdout


def staged_files(root: Path) -> dict[str, str]:
    output = run_git(root, ["ls-files", "-z", "--", ".phaseharness"])
    managed: dict[str, str] = {}
    for raw in output.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8")
        if not is_managed_path(rel):
            continue
        data = run_git(root, ["show", f":{rel}"])
        managed[rel] = sha256_bytes(data)
    return managed


def build_manifest(root: Path, *, staged: bool, version: str | None, revision: str | None) -> dict[str, Any]:
    manifest_path = root / MANIFEST_PATH
    manifest = load_manifest(manifest_path)
    manifest["schema_version"] = manifest.get("schema_version", 1)
    if version is not None:
        manifest["version"] = version
    else:
        manifest["version"] = manifest.get("version", "0.1.1")
    if revision is not None:
        manifest["revision"] = revision
    else:
        manifest["revision"] = manifest.get("revision", "local")
    manifest["managed_files"] = staged_files(root) if staged else working_tree_files(root)
    return manifest


def manifest_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def command_write(args: argparse.Namespace) -> int:
    root = find_project_root()
    manifest = build_manifest(root, staged=args.staged, version=args.version, revision=args.revision)
    (root / MANIFEST_PATH).write_text(manifest_text(manifest))
    return 0


def command_check(args: argparse.Namespace) -> int:
    root = find_project_root()
    expected = manifest_text(build_manifest(root, staged=args.staged, version=args.version, revision=args.revision))
    actual_path = root / MANIFEST_PATH
    actual = actual_path.read_text() if actual_path.exists() else ""
    if actual == expected:
        return 0
    print(".phaseharness/manifest.json is stale.")
    print("Run:")
    staged_flag = " --staged" if args.staged else ""
    print(f"python3 scripts/phaseharness-refresh-manifest.py write{staged_flag}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Phaseharness managed file hashes.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--staged", action="store_true", help="hash staged index contents instead of working tree files")
        command.add_argument("--version", help="set manifest version")
        command.add_argument("--revision", help="set manifest revision")

    write = sub.add_parser("write", help="write .phaseharness/manifest.json")
    add_common(write)
    check = sub.add_parser("check", help="verify .phaseharness/manifest.json")
    add_common(check)
    args = parser.parse_args()

    if args.command == "write":
        return command_write(args)
    if args.command == "check":
        return command_check(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
