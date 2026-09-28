"""Shared CLI lookup for restart preflight and the background launcher.

Also executable directly by run.sh; keep this module standard-library only.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


def resolve_agent_cli(agent: str, *, path: str | None = None) -> str:
    command = {"claude": "claude", "codex": "codex",
               "cursor": "agent", "agent": "agent"}.get(agent)
    if command is None:
        raise ValueError(f"unsupported agent: {agent}")
    found = shutil.which(command, path=path)
    if found:
        # Preserve installer-managed symlinks instead of pinning a version.
        return os.path.abspath(found)
    local = Path.home() / ".local" / "bin" / command
    if local.is_file() and os.access(local, os.X_OK):
        return str(local.absolute())
    raise FileNotFoundError(
        f"{command} executable not found in PATH or ~/.local/bin; "
        "install the CLI or configure the Dashboard service PATH"
    )


if __name__ == "__main__":
    try:
        print(resolve_agent_cli(sys.argv[1]))
    except (OSError, ValueError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(127)
