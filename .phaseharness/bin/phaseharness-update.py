#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPO_URL = "https://github.com/Ssoon-m/phaseharness.git"
DEFAULT_REF = "main"
PROTECTED_PREFIXES = (
    ".phaseharness/runs/",
    ".phaseharness/state/",
)
PROTECTED_FILES = {
    ".phaseharness/context.json",
    ".phaseharness/settings.json",
}
SETTINGS_PATH = Path(".phaseharness") / "settings.json"


@dataclass(frozen=True)
class Plan:
    local_version: str
    source_version: str
    updated: list[str]
    skipped: list[str]
    unchanged: list[str]


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".phaseharness" / "manifest.json").is_file() or (current / ".phaseharness").is_dir():
            return current
        current = current.parent
    raise RuntimeError("could not find phaseharness root")


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        raise RuntimeError(f"could not read JSON: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return data


def load_optional_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json_object(path)


def setting_enabled(value: Any, path: Path) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    raise RuntimeError(f"settings update.enabled must be a boolean: {path}")


def update_enabled(root: Path) -> bool:
    env_value = os.environ.get("PHASEHARNESS_UPDATE")
    if env_value == "0":
        return False
    if env_value == "1":
        return True
    path = root / SETTINGS_PATH
    settings = load_optional_json_object(path)
    update = settings.get("update", {})
    if update == {}:
        return True
    if not isinstance(update, dict):
        raise RuntimeError(f"settings update must be an object: {path}")
    return setting_enabled(update.get("enabled"), path)


def managed_files(manifest: dict[str, Any], path: Path) -> dict[str, str]:
    value = manifest.get("managed_files")
    if not isinstance(value, dict):
        raise RuntimeError(f"manifest managed_files must be an object: {path}")
    files: dict[str, str] = {}
    for rel, digest in value.items():
        if not isinstance(rel, str) or not isinstance(digest, str):
            raise RuntimeError(f"manifest managed_files entries must be strings: {path}")
        files[rel] = digest
    return files


def normalize_update_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"update path must be a relative path inside the project: {value}")
    normalized = path.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def file_digest(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def is_protected(rel: str) -> bool:
    return rel in PROTECTED_FILES or any(rel.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def parse_version(value: str) -> tuple[int, ...] | None:
    parts = value.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def compare_versions(left: str, right: str) -> int:
    left_version = parse_version(left)
    right_version = parse_version(right)
    if left_version is None or right_version is None:
        return 0
    width = max(len(left_version), len(right_version))
    padded_left = left_version + (0,) * (width - len(left_version))
    padded_right = right_version + (0,) * (width - len(right_version))
    return (padded_left > padded_right) - (padded_left < padded_right)


def clone_source(repo_url: str, ref: str, timeout_seconds: float) -> tempfile.TemporaryDirectory[str]:
    tempdir = tempfile.TemporaryDirectory(prefix="phaseharness-update.")
    source = Path(tempdir.name) / "source"
    command = ["git", "clone", "--depth=1"]
    if ref:
        command.extend(["--branch", ref])
    command.extend([repo_url, str(source)])
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        tempdir.cleanup()
        raise RuntimeError(f"phaseharness update check timed out after {timeout_seconds:g}s") from exc
    except subprocess.CalledProcessError as exc:
        tempdir.cleanup()
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"could not fetch phaseharness update source: {detail}") from exc
    return tempdir


def source_root(args: argparse.Namespace) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    source = args.source or os.environ.get("PHASEHARNESS_SOURCE")
    if source:
        path = Path(source).expanduser().resolve()
        if not (path / ".phaseharness" / "manifest.json").is_file():
            raise RuntimeError(f"source is missing .phaseharness/manifest.json: {path}")
        return path, None
    repo_url = args.repo_url or os.environ.get("PHASEHARNESS_REPO_URL", DEFAULT_REPO_URL)
    ref = args.ref or os.environ.get("PHASEHARNESS_UPDATE_REF", DEFAULT_REF)
    tempdir = clone_source(repo_url, ref, args.timeout_seconds)
    return Path(tempdir.name) / "source", tempdir


def build_plan(root: Path, source: Path, overwrite: set[str] | None = None) -> tuple[Plan, dict[str, Any]]:
    local_manifest_path = root / ".phaseharness" / "manifest.json"
    source_manifest_path = source / ".phaseharness" / "manifest.json"
    local_manifest = load_json_object(local_manifest_path)
    source_manifest = load_json_object(source_manifest_path)
    local_files = managed_files(local_manifest, local_manifest_path)
    source_files = managed_files(source_manifest, source_manifest_path)
    local_version = str(local_manifest.get("version", "unknown"))
    source_version = str(source_manifest.get("version", "unknown"))

    updated: list[str] = []
    skipped: list[str] = []
    unchanged: list[str] = []
    overwrite = overwrite or set()

    if compare_versions(source_version, local_version) < 0:
        return Plan(local_version=local_version, source_version=source_version, updated=[], skipped=[], unchanged=[]), source_manifest

    unknown_overwrites = sorted(path for path in overwrite if path not in source_files)
    if unknown_overwrites:
        raise RuntimeError(f"overwrite path is not managed by source manifest: {', '.join(unknown_overwrites)}")

    for rel, source_expected in sorted(source_files.items()):
        if is_protected(rel):
            skipped.append(rel)
            continue
        source_path = source / rel
        source_actual = file_digest(source_path)
        if source_actual != source_expected:
            raise RuntimeError(f"source manifest hash mismatch: {rel}")
        local_path = root / rel
        local_actual = file_digest(local_path)
        if local_actual == source_expected:
            unchanged.append(rel)
            continue
        if rel in overwrite:
            updated.append(rel)
            continue
        local_expected = local_files.get(rel)
        if local_actual is None or (local_expected is not None and local_actual == local_expected):
            updated.append(rel)
        else:
            skipped.append(rel)

    return (
        Plan(
            local_version=local_version,
            source_version=source_version,
            updated=updated,
            skipped=skipped,
            unchanged=unchanged,
        ),
        source_manifest,
    )


def copy_managed_file(source: Path, root: Path, rel: str) -> None:
    source_path = source / rel
    target_path = root / rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.is_symlink():
        target_path.unlink()
    shutil.copy2(source_path, target_path)


def apply_plan(root: Path, source: Path, plan: Plan, source_manifest: dict[str, Any]) -> None:
    for rel in plan.updated:
        copy_managed_file(source, root, rel)
    manifest_path = root / ".phaseharness" / "manifest.json"
    manifest = load_json_object(manifest_path)
    local_files = managed_files(manifest, manifest_path)
    source_files = managed_files(source_manifest, source / ".phaseharness" / "manifest.json")
    for rel in plan.updated:
        local_files[rel] = source_files[rel]
    manifest["managed_files"] = {rel: local_files[rel] for rel in sorted(local_files)}
    for key in ("schema_version", "version", "revision"):
        if key in source_manifest:
            manifest[key] = source_manifest[key]
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def print_plan(plan: Plan, applied: bool, quiet: bool) -> None:
    if quiet and not plan.updated and not plan.skipped:
        return
    if plan.updated:
        label = "Phaseharness updated:" if applied else "Phaseharness can update:"
        print(label)
        for rel in plan.updated:
            print(f"- {rel}")
    elif not quiet and not plan.skipped:
        print(f"Phaseharness is up to date ({plan.local_version}).")
    elif not quiet:
        print("No safe Phaseharness updates applied.")
    if plan.skipped:
        print("Phaseharness found local changes that need your decision:")
        for rel in plan.skipped:
            print(f"- {rel}")
        print("Ask the user whether to overwrite these files with the upstream Phaseharness versions.")
        print("After approval, run:")
        overwrite_args = " ".join(f"--overwrite {shlex.quote(rel)}" for rel in plan.skipped)
        print(f"python3 .phaseharness/bin/phaseharness-update.py apply {overwrite_args}")


def command_check(args: argparse.Namespace) -> int:
    root = find_project_root()
    if not update_enabled(root):
        if not args.quiet:
            print("Phaseharness updates are disabled.")
        return 0
    source, tempdir = source_root(args)
    try:
        plan, _ = build_plan(root, source)
        print_plan(plan, applied=False, quiet=args.quiet)
    finally:
        if tempdir is not None:
            tempdir.cleanup()
    return 0


def command_apply(args: argparse.Namespace) -> int:
    root = find_project_root()
    if not update_enabled(root):
        if not args.quiet:
            print("Phaseharness updates are disabled.")
        return 0
    source, tempdir = source_root(args)
    try:
        overwrite = {normalize_update_path(path) for path in args.overwrite}
        plan, source_manifest = build_plan(root, source, overwrite=overwrite)
        if plan.updated:
            apply_plan(root, source, plan, source_manifest)
        print_plan(plan, applied=True, quiet=args.quiet)
    finally:
        if tempdir is not None:
            tempdir.cleanup()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and apply safe Phaseharness updates.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--source", help="local phaseharness checkout to update from")
        command.add_argument("--repo-url", help="phaseharness git repository URL")
        command.add_argument("--ref", help="phaseharness git ref to update from")
        command.add_argument(
            "--timeout-seconds",
            type=float,
            default=float(os.environ.get("PHASEHARNESS_UPDATE_TIMEOUT_SECONDS", "8")),
        )
        command.add_argument("--quiet", action="store_true")

    check = sub.add_parser("check", help="check for safe updates")
    add_common_options(check)
    apply = sub.add_parser("apply", help="apply safe updates and skip locally modified files")
    add_common_options(apply)
    apply.add_argument(
        "--overwrite",
        action="append",
        default=[],
        help="overwrite a locally modified managed file after user approval",
    )
    args = parser.parse_args()

    if args.command == "check":
        return command_check(args)
    if args.command == "apply":
        return command_apply(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
