"""Dependency-free repository checks shared by contributors, agents and CI."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tokenize


ROOT = Path(__file__).resolve().parents[1]


def local_path(root: Path, value: str) -> Path:
    """Accept repository-relative paths, including Git-worktree checkouts."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value == ".":
        raise ValueError(f"Path escapes repository: {value!r}")
    resolved = (root / value).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes repository: {value!r}")
    return root / value


def matching_files(root: Path, patterns: list[str]) -> list[Path]:
    found: set[Path] = set()
    if not isinstance(patterns, list) or not patterns:
        raise ValueError("Expected a nonempty list of file patterns")
    for pattern in patterns:
        local_path(root, pattern)
        matches = [p for p in root.glob(pattern) if p.is_file()]
        if not matches:
            raise ValueError(f"Pattern matches no files: {pattern}")
        for path in matches:
            local_path(root, path.relative_to(root).as_posix())
        found.update(matches)
    return sorted(found)


def load_workspace(root: Path) -> dict:
    data = json.loads((root / "workspace.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported workspace schema")
    components = data.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError("Workspace has no components")
    roots = []
    for name, component in components.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or not isinstance(component, dict):
            raise ValueError(f"Invalid component: {name}")
        source = local_path(root, component["root"])
        if not source.is_dir():
            raise ValueError(f"Missing component root: {source}")
        for previous in roots:
            if source.resolve().is_relative_to(previous) or previous.is_relative_to(source.resolve()):
                raise ValueError(f"Overlapping component root: {source}")
        roots.append(source.resolve())
        if not isinstance(component.get("role"), str) or not component["role"].strip():
            raise ValueError(f"Missing component role: {name}")
        blocked = component.get("forbidden_imports", [])
        if not isinstance(blocked, list) or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-zA-Z_]\w*", item)
            for item in blocked
        ):
            raise ValueError(f"Invalid import boundary: {name}")
        matching_files(root, component["entrypoints"])
        matching_files(root, component["tests"])
        if not local_path(root, component["guide"]).is_file():
            raise ValueError(f"Missing component guide: {name}")
    checks = data["checks"]
    for kind in ("python", "shell", "javascript", "json"):
        matching_files(root, checks[kind])
    if not local_path(root, checks["inline_script"]).is_file():
        raise ValueError("Missing inline-script source")
    return data


def run(command: list[str], root: Path, *, source: str | None = None) -> None:
    subprocess.run(command, cwd=root, input=source, text=True, check=True, timeout=60)


def check_import_boundaries(root: Path, workspace: dict) -> None:
    """Enforce declared absolute Python import boundaries, not a dynamic graph."""
    for name, component in workspace["components"].items():
        blocked = set(component.get("forbidden_imports", []))
        if not blocked:
            continue
        for path in local_path(root, component["root"]).rglob("*.py"):
            local_path(root, path.relative_to(root).as_posix())
            with tokenize.open(path) as source:
                tree = ast.parse(source.read(), filename=str(path))
            for node in ast.walk(tree):
                imports = []
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imports = [node.module]
                for imported in imports:
                    if imported.split(".")[0] in blocked:
                        raise ValueError(f"{name}: forbidden import {imported} at {path.relative_to(root)}:{node.lineno}")


def check_sources(root: Path, workspace: dict) -> None:
    check_import_boundaries(root, workspace)
    checks = workspace["checks"]
    for path in matching_files(root, checks["python"]):
        # Compile without importing application modules or writing __pycache__.
        with tokenize.open(path) as source:
            compile(source.read(), str(path), "exec")
    for path in matching_files(root, checks["shell"]):
        # bash -n a.sh b.sh checks only a.sh; check every file separately.
        run(["bash", "-n", str(path)], root)
    for path in matching_files(root, checks["javascript"]):
        run(["node", "--check", str(path)], root)
    for path in matching_files(root, checks["json"]):
        json.loads(path.read_text(encoding="utf-8"))
    html = local_path(root, checks["inline_script"]).read_text(encoding="utf-8")
    start = html.rfind("<script>")
    end = html.find("</script>", start)
    if start < 0 or end < 0:
        raise ValueError("Dashboard inline script block missing")
    run(["node", "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"],
        root, source=html[start + len("<script>"):end])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--map", action="store_true", help="Print validated workspace JSON")
    mode.add_argument("--structure", action="store_true", help="Validate layout only; no external tools")
    args = parser.parse_args(argv)
    try:
        workspace = load_workspace(ROOT)
        if args.map:
            print(json.dumps(workspace, ensure_ascii=False, indent=2))
            return 0
        if not args.structure:
            check_sources(ROOT, workspace)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, subprocess.SubprocessError) as exc:
        print(f"Repository check failed: {exc}", file=sys.stderr)
        return 1
    print("Repository structure OK" if args.structure else "Repository structure and syntax OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
