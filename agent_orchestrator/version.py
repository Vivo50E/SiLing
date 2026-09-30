"""Local build identity; capture once when constructing the Dashboard app."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


VERSION = "0.3.0"


def build_info(repo_dir: Path) -> dict[str, str | bool | None]:
    """Identify this checkout, never the remote or an enclosing repository.

    The commit suffix changes automatically for every committed update. Source
    archives and unavailable Git are explicitly unknown, not release builds.
    No paths, remotes, or subprocess error output leave this function.
    """
    info: dict[str, str | bool | None] = {
        "version": f"{VERSION}+unknown", "base_version": VERSION,
        "commit": None, "dirty": None,
    }
    if not (repo_dir / ".git").exists():
        return info
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    env["GIT_OPTIONAL_LOCKS"] = "0"

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo_dir), *args], env=env,
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "--verify", "HEAD")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return info
        info["commit"] = commit
        info["version"] = f"{VERSION}+g{commit[:12]}"
        dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
        info["dirty"] = dirty
        if dirty:
            info["version"] += ".dirty"
    except (OSError, subprocess.SubprocessError, UnicodeError):
        if info["commit"]:
            info["version"] += ".unknown"
    return info
