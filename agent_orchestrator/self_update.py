"""Review and fast-forward approved self-improvement branches safely."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Optional


SELF_IMPROVEMENT_BRANCH_PREFIX = "agent/self-improve-"
VERIFY_TTL_SECONDS = 15 * 60
MAX_OUTPUT_CHARS = 16_000


class SelfUpdateError(RuntimeError):
    """An update cannot be reviewed or applied safely."""


class SelfUpdateManager:
    """Discover, verify, and fast-forward isolated improvement branches.

    Candidate code is never copied from a dirty working tree. An agent must
    commit its result on an ``agent/self-improve-*`` branch. Verification is
    bound to the exact target and candidate commits, so any subsequent change
    invalidates the approval token.
    """

    def __init__(self, repo_dir: Path, *, python: Optional[str] = None):
        self.repo_dir = repo_dir.resolve()
        self.python = python or sys.executable
        self._verified: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._fetch_lock = threading.Lock()

    def _git(
        self,
        *args: str,
        cwd: Optional[Path] = None,
        timeout: float = 30,
        check: bool = True,
        extra_env: Optional[dict[str, str]] = None,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.setdefault("GIT_OPTIONAL_LOCKS", "0")
        if extra_env:
            env.update(extra_env)
        try:
            result = subprocess.run(
                ["git", *args], cwd=str(cwd or self.repo_dir), env=env,
                capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SelfUpdateError(f"git {' '.join(args)} failed: {exc}") from exc
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise SelfUpdateError(
                f"git {' '.join(args)} failed: {detail or result.returncode}"
            )
        return result

    def _target(self) -> tuple[str, str, bool]:
        branch = self._git("branch", "--show-current").stdout.strip()
        if not branch:
            raise SelfUpdateError("dashboard repository is on a detached HEAD")
        head = self._git("rev-parse", "HEAD").stdout.strip()
        dirty = bool(self._git("status", "--porcelain").stdout.strip())
        return branch, head, dirty

    def _worktrees(self) -> list[dict[str, str]]:
        raw = self._git("worktree", "list", "--porcelain").stdout
        records: list[dict[str, str]] = []
        for block in raw.strip().split("\n\n"):
            record: dict[str, str] = {}
            for line in block.splitlines():
                key, _, value = line.partition(" ")
                if key in {"worktree", "HEAD", "branch"}:
                    record[key] = value
            if record.get("worktree") and record.get("branch"):
                records.append(record)
        return records

    def _agent_candidate(self, branch: str) -> dict[str, Any]:
        if not branch.startswith(SELF_IMPROVEMENT_BRANCH_PREFIX):
            raise SelfUpdateError("only agent/self-improve-* branches are eligible")
        target_branch, target_head, target_dirty = self._target()
        match = None
        for record in self._worktrees():
            name = record["branch"].removeprefix("refs/heads/")
            if name == branch:
                match = record
                break
        if match is None:
            raise SelfUpdateError("candidate branch is not checked out in a worktree")

        worktree = Path(match["worktree"]).resolve()
        candidate_head = self._git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        counts = self._git(
            "rev-list", "--left-right", "--count",
            f"{target_head}...{candidate_head}",
        ).stdout.split()
        behind, ahead = (int(counts[0]), int(counts[1]))
        dirty_text = self._git("status", "--porcelain", cwd=worktree).stdout.strip()
        files = []
        if ahead:
            for line in self._git(
                "diff", "--name-status", f"{target_head}..{candidate_head}"
            ).stdout.splitlines():
                status, _, path = line.partition("\t")
                files.append({"status": status, "path": path})
        commits = []
        if ahead:
            for line in self._git(
                "log", "--format=%H%x09%h%x09%s", "--max-count=20",
                f"{target_head}..{candidate_head}",
            ).stdout.splitlines():
                sha, short, subject = (line.split("\t", 2) + ["", ""])[:3]
                commits.append({"sha": sha, "short": short, "subject": subject})
        diffstat = (
            self._git("diff", "--stat", f"{target_head}..{candidate_head}")
            .stdout.strip()
        ) if ahead else ""
        blocked = ""
        if target_dirty:
            blocked = "dashboard repository has uncommitted changes"
        elif dirty_text:
            blocked = "candidate worktree has uncommitted changes"
        elif behind:
            blocked = "candidate does not fast-forward the current branch"
        elif not ahead:
            blocked = "candidate has no unapplied commits"
        return {
            "kind": "agent",
            "branch": branch,
            "worktree": str(worktree),
            "head": candidate_head,
            "short_head": candidate_head[:12],
            "target_branch": target_branch,
            "target_head": target_head,
            "ahead": ahead,
            "behind": behind,
            "dirty": bool(dirty_text),
            "target_dirty": target_dirty,
            "eligible": not blocked,
            "blocked_reason": blocked,
            "files": files,
            "commits": commits,
            "diffstat": diffstat,
        }

    def _upstream_ref(self) -> str:
        target_branch, _target_head, _target_dirty = self._target()
        configured = self._git(
            "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}",
            check=False,
        ).stdout.strip()
        refs = [configured] if configured else []
        remotes = self._git("remote", check=False).stdout.split()
        if "origin" in remotes:
            refs.extend((f"origin/{target_branch}", "origin/main"))
        for remote in remotes:
            refs.extend((f"{remote}/{target_branch}", f"{remote}/main"))
        seen: set[str] = set()
        for ref in refs:
            if not ref or ref in seen:
                continue
            seen.add(ref)
            exists = self._git(
                "show-ref", "--verify", "--quiet", f"refs/remotes/{ref}",
                check=False,
            )
            if exists.returncode == 0:
                return ref
        return ""

    def _upstream_candidate(self, candidate_id: str = "") -> dict[str, Any]:
        upstream_ref = self._upstream_ref()
        if not upstream_ref:
            raise SelfUpdateError("no upstream branch is configured or available")
        key = f"upstream:{upstream_ref}"
        if candidate_id and candidate_id != key:
            raise SelfUpdateError("upstream candidate no longer matches configuration")
        target_branch, target_head, target_dirty = self._target()
        candidate_head = self._git("rev-parse", upstream_ref).stdout.strip()
        counts = self._git(
            "rev-list", "--left-right", "--count",
            f"{target_head}...{candidate_head}",
        ).stdout.split()
        behind, ahead = (int(counts[0]), int(counts[1]))
        files = []
        if ahead:
            for line in self._git(
                "diff", "--name-status", f"{target_head}..{candidate_head}"
            ).stdout.splitlines():
                status, _, path = line.partition("\t")
                files.append({"status": status, "path": path})
        commits = []
        if ahead:
            for line in self._git(
                "log", "--format=%H%x09%h%x09%s", "--max-count=20",
                f"{target_head}..{candidate_head}",
            ).stdout.splitlines():
                sha, short, subject = (line.split("\t", 2) + ["", ""])[:3]
                commits.append({"sha": sha, "short": short, "subject": subject})
        diffstat = (
            self._git("diff", "--stat", f"{target_head}..{candidate_head}")
            .stdout.strip()
        ) if ahead else ""
        blocked = ""
        if target_dirty:
            blocked = "dashboard repository has uncommitted changes"
        elif behind:
            blocked = "current branch has commits not in upstream; cannot fast-forward"
        elif not ahead:
            blocked = "upstream has no unapplied commits"
        return {
            "kind": "upstream",
            "branch": key,
            "source": upstream_ref,
            "worktree": "temporary detached worktree during verification",
            "head": candidate_head,
            "short_head": candidate_head[:12],
            "target_branch": target_branch,
            "target_head": target_head,
            "ahead": ahead,
            "behind": behind,
            "dirty": False,
            "target_dirty": target_dirty,
            "eligible": not blocked,
            "blocked_reason": blocked,
            "files": files,
            "commits": commits,
            "diffstat": diffstat,
        }

    def _candidate(self, candidate_id: str) -> dict[str, Any]:
        if candidate_id.startswith("upstream:"):
            return self._upstream_candidate(candidate_id)
        return self._agent_candidate(candidate_id)

    def fetch_upstream(self) -> dict[str, Any]:
        """Refresh remote-tracking refs without changing the working tree."""
        target_branch, _target_head, _target_dirty = self._target()
        configured_remote = self._git(
            "config", "--get", f"branch.{target_branch}.remote", check=False,
        ).stdout.strip()
        remotes = self._git("remote", check=False).stdout.split()
        remote = configured_remote if configured_remote in remotes else ""
        if not remote and "origin" in remotes:
            remote = "origin"
        if not remote and remotes:
            remote = remotes[0]
        if not remote:
            raise SelfUpdateError("repository has no Git remote")
        with self._fetch_lock:
            result = self._git(
                "fetch", "--prune", remote, timeout=60,
                extra_env={"GIT_TERMINAL_PROMPT": "0"},
            )
        return {
            "ok": True,
            "remote": remote,
            "output": (result.stdout or result.stderr).strip(),
        }

    @staticmethod
    def _fingerprint(candidate: dict[str, Any]) -> str:
        raw = ":".join((
            candidate["target_head"], candidate["head"], candidate["branch"]
        ))
        return hashlib.sha256(raw.encode()).hexdigest()

    def status(self) -> dict[str, Any]:
        try:
            target_branch, target_head, target_dirty = self._target()
        except SelfUpdateError as exc:
            return {"available": False, "error": str(exc), "candidates": []}
        candidates = []
        for record in self._worktrees():
            branch = record["branch"].removeprefix("refs/heads/")
            if (branch.startswith(SELF_IMPROVEMENT_BRANCH_PREFIX)
                    and Path(record["worktree"]).resolve() != self.repo_dir):
                try:
                    candidates.append(self._agent_candidate(branch))
                except SelfUpdateError as exc:
                    candidates.append({
                        "branch": branch, "eligible": False,
                        "blocked_reason": str(exc), "ahead": 0,
                        "behind": 0, "files": [], "commits": [],
                    })
        try:
            candidates.append(self._upstream_candidate())
        except SelfUpdateError:
            pass
        # An ancestor (or identical ref) contains no code that can be applied.
        # Do not present it as a blocked update merely because the local branch
        # has moved ahead after a successful rebase or local fix.
        candidates = [
            candidate for candidate in candidates
            if candidate.get("ahead") != 0 or not candidate.get("head")
        ]
        candidates.sort(key=lambda item: (
            not item.get("eligible"),
            item.get("kind") != "upstream",
            item["branch"],
        ))
        unique_candidates = []
        seen_heads: set[tuple[str, str]] = set()
        for candidate in candidates:
            identity = (
                str(candidate.get("target_head") or target_head),
                str(candidate.get("head") or ""),
            )
            if identity[1] and identity in seen_heads:
                continue
            if identity[1]:
                seen_heads.add(identity)
            unique_candidates.append(candidate)
        candidates = unique_candidates
        return {
            "available": True,
            "target_branch": target_branch,
            "target_head": target_head,
            "target_dirty": target_dirty,
            "candidate_prefix": SELF_IMPROVEMENT_BRANCH_PREFIX,
            "candidates": candidates,
        }

    def _verification_environment(self) -> dict[str, str]:
        env = dict(os.environ)
        python = shutil.which(self.python) or self.python
        # Do not resolve symlinks: .venv/bin/python may point to a system
        # binary, but its directory selects the runtime's dependencies for
        # nested `python3` and `#!/usr/bin/env python3` invocations.
        runtime_bin = str(Path(python).absolute().parent)
        env["PATH"] = runtime_bin + os.pathsep + env.get("PATH", os.defpath)
        return env

    def verify(self, branch: str, *, timeout: float = 300) -> dict[str, Any]:
        candidate = self._candidate(branch)
        if not candidate["eligible"]:
            raise SelfUpdateError(candidate["blocked_reason"])
        command = [
            self.python, "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_*.py", "-q",
        ]
        started = time.monotonic()
        test_dir = Path(candidate["worktree"])
        temporary_root: Optional[Path] = None
        temporary_worktree: Optional[Path] = None
        try:
            if candidate.get("kind") == "upstream":
                temporary_root = Path(tempfile.mkdtemp(prefix="siling-upstream-"))
                temporary_worktree = temporary_root / "checkout"
                self._git(
                    "worktree", "add", "--detach", str(temporary_worktree),
                    candidate["head"], timeout=60,
                )
                test_dir = temporary_worktree
            result = subprocess.run(
                command, cwd=str(test_dir), capture_output=True,
                text=True, timeout=timeout, env=self._verification_environment(),
            )
            output = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            count_match = re.search(r"Ran\s+([0-9,]+)\s+tests?", output)
            test_count = int(count_match.group(1).replace(",", "")) if count_match else 0
            passed = result.returncode == 0 and test_count > 0
            if result.returncode == 0 and not test_count:
                output += "\nVerification rejected: the suite reported no tests."
        except subprocess.TimeoutExpired as exc:
            output = f"test suite timed out after {timeout:g}s"
            if exc.stdout:
                output += "\n" + str(exc.stdout)
            passed = False
            test_count = 0
        except (OSError, SelfUpdateError) as exc:
            output = f"could not prepare or run test suite: {exc}"
            passed = False
            test_count = 0
        finally:
            if temporary_worktree is not None:
                self._git(
                    "worktree", "remove", "--force", str(temporary_worktree),
                    timeout=60, check=False,
                )
                shutil.rmtree(temporary_root, ignore_errors=True)
        duration = round(time.monotonic() - started, 3)
        response: dict[str, Any] = {
            "ok": passed,
            "branch": branch,
            "target_head": candidate["target_head"],
            "candidate_head": candidate["head"],
            "duration_seconds": duration,
            "test_count": test_count,
            "output": output[-MAX_OUTPUT_CHARS:],
        }
        if passed:
            token = secrets.token_urlsafe(32)
            with self._lock:
                self._verified[token] = {
                    "branch": branch,
                    "fingerprint": self._fingerprint(candidate),
                    "expires_at": time.time() + VERIFY_TTL_SECONDS,
                }
            response.update({
                "verification_token": token,
                "expires_in_seconds": VERIFY_TTL_SECONDS,
            })
        return response

    def apply(self, branch: str, token: str, confirmation: str) -> dict[str, Any]:
        if confirmation != "APPROVE":
            raise SelfUpdateError("confirmation must exactly equal APPROVE")
        with self._lock:
            verified = self._verified.get(token)
        if not verified or verified.get("branch") != branch:
            raise SelfUpdateError("verification token is missing or invalid")
        if float(verified.get("expires_at") or 0) < time.time():
            raise SelfUpdateError("verification token has expired; run tests again")

        candidate = self._candidate(branch)
        if not candidate["eligible"]:
            raise SelfUpdateError(candidate["blocked_reason"])
        if verified.get("fingerprint") != self._fingerprint(candidate):
            raise SelfUpdateError("target or candidate changed after verification")
        # Merge the exact verified object, not the movable branch name.
        result = self._git("merge", "--ff-only", candidate["head"], timeout=60)
        new_head = self._git("rev-parse", "HEAD").stdout.strip()
        with self._lock:
            self._verified.pop(token, None)
        return {
            "ok": True,
            "branch": branch,
            "previous_head": candidate["target_head"],
            "head": new_head,
            "short_head": new_head[:12],
            "merge_output": (result.stdout or result.stderr).strip(),
            "restart_required": True,
        }
