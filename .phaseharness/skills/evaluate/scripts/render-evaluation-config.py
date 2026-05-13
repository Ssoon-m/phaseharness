#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Render evaluate context config as markdown.")
    parser.add_argument("--run-id", default="", help="Optional run id used to replace <run-id> in configured rules.")
    args = parser.parse_args()

    root = find_project_root(Path(__file__).parent)
    config = load_config(root)
    print("# Evaluation Config")
    print()
    if config is None:
        print("No active `.phaseharness/context.json`.")
        return 0
    evaluate = config.get("evaluate", {})
    docs = evaluate.get("documents", []) if isinstance(evaluate, dict) else []
    rules = evaluate.get("rules", []) if isinstance(evaluate, dict) else []

    if isinstance(docs, list) and docs:
        print("## Documents")
        for item in docs:
            print("\n".join(render_doc(root, item)))
    else:
        print("No configured evaluation documents.")

    if isinstance(rules, list) and rules:
        print()
        print("## Rules")
        for rule in rules:
            text = str(rule)
            if args.run_id:
                text = text.replace("<run-id>", args.run_id)
            print(f"- {text}")
    else:
        print("No configured evaluation rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
