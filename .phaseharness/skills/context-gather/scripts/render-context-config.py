#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    while current != current.parent:
        if (current / ".phaseharness").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    raise RuntimeError("could not find project root")


def load_config(root: Path) -> dict[str, Any] | None:
    path = root / ".phaseharness" / "context.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise RuntimeError(".phaseharness/context.json must be a JSON object")
    return data


def doc_status(root: Path, item: dict[str, Any]) -> tuple[str, list[str]]:
    root_resolved = root.resolve()
    if "path" in item:
        path = (root / str(item["path"])).resolve()
        try:
            rel = path.relative_to(root_resolved)
        except ValueError:
            return "invalid", []
        if not path.exists():
            return "missing", []
        if not path.is_file():
            return "not_a_file", []
        try:
            with path.open("r", encoding="utf-8"):
                pass
        except OSError:
            return "unreadable", []
        return "exists", [str(rel)]
    if "glob" in item:
        pattern = str(item["glob"])
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            return "invalid", []
        try:
            paths = sorted(path for path in root.glob(pattern) if path.is_file())
            matches = [str(path.resolve().relative_to(root_resolved)) for path in paths]
        except (ValueError, NotImplementedError, OSError):
            return "invalid", []
        if not matches:
            return "no_matches", []
        return "matched", matches
    return "invalid", []


def render_doc(root: Path, item: Any) -> list[str]:
    if not isinstance(item, dict):
        return ["- invalid entry: not an object"]
    source_key = "path" if "path" in item else "glob" if "glob" in item else "source"
    source = str(item.get(source_key, ""))
    status, matches = doc_status(root, item)
    priority = item.get("priority", "unspecified")
    description = item.get("description", "")
    line = f"- `{source}` ({source_key}, {priority}, {status})"
    if description:
        line += f": {description}"
    lines = [line]
    if matches and source_key == "glob":
        shown = matches[:8]
        lines.append("  matches: " + ", ".join(f"`{match}`" for match in shown))
        if len(matches) > len(shown):
            lines.append(f"  more: {len(matches) - len(shown)}")
    return lines


def main() -> int:
    root = find_project_root(Path(__file__).parent)
    config = load_config(root)
    print("# Context-Gather Config")
    print()
    if config is None:
        print("No active `.phaseharness/context.json`.")
        return 0
    docs = config.get("context-gather", {}).get("documents", [])
    if not isinstance(docs, list) or not docs:
        print("No configured context-gather documents.")
        return 0
    for item in docs:
        print("\n".join(render_doc(root, item)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
