import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent_orchestrator import dashboard, version


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Version Test")
        self.git("config", "user.email", "version@example.invalid")
        self.git("commit", "--allow-empty", "-m", "initial")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()

    def test_each_commit_changes_build_identity_without_bumping_base(self):
        first = version.build_info(self.repo)
        self.assertEqual(first["version"], f'{version.VERSION}+g{self.git("rev-parse", "HEAD")[:12]}')
        self.assertFalse(first["dirty"])
        self.git("commit", "--allow-empty", "-m", "next update")
        second = version.build_info(self.repo)
        self.assertNotEqual(first["version"], second["version"])
        self.assertEqual(first["base_version"], second["base_version"])

    def test_worktree_detached_head_and_untracked_changes(self):
        worktree = self.root / "detached"
        self.git("worktree", "add", "--detach", str(worktree), "HEAD")
        self.assertEqual(version.build_info(worktree), version.build_info(self.repo))
        (worktree / "private.txt").write_text("private data", encoding="utf-8")
        result = version.build_info(worktree)
        self.assertTrue(result["dirty"])
        self.assertTrue(result["version"].endswith(".dirty"))
        self.assertNotIn("private", str(result))
        self.assertNotIn(str(self.root), str(result))

    def test_staged_and_unstaged_changes_are_marked(self):
        tracked = self.repo / "tracked.txt"
        tracked.write_text("base", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.assertTrue(version.build_info(self.repo)["dirty"])
        self.git("commit", "-m", "track file")
        self.assertFalse(version.build_info(self.repo)["dirty"])
        tracked.write_text("changed", encoding="utf-8")
        self.assertTrue(version.build_info(self.repo)["dirty"])

    def test_archive_does_not_inherit_enclosing_repository_version(self):
        archive = self.repo / "archive"
        archive.mkdir()
        with patch.object(version.subprocess, "run") as run:
            result = version.build_info(archive)
        run.assert_not_called()
        self.assertEqual(result["version"], f"{version.VERSION}+unknown")
        self.assertIsNone(result["commit"])

    def test_git_failure_is_bounded_and_does_not_expose_errors(self):
        for error in (FileNotFoundError("private path"),
                      subprocess.TimeoutExpired("git private", 3),
                      subprocess.CalledProcessError(1, "git", stderr="private")):
            with self.subTest(error=type(error)), patch.object(version.subprocess, "run", side_effect=error) as run:
                result = version.build_info(self.repo)
                self.assertEqual(result["version"], f"{version.VERSION}+unknown")
                self.assertNotIn("private", str(result))
                self.assertEqual(run.call_args.kwargs["timeout"], 3)

    def test_failed_status_does_not_claim_clean_build(self):
        commit = "a" * 40
        with patch.object(version.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 0, stdout=commit),
            subprocess.TimeoutExpired("git", 3),
        ]):
            result = version.build_info(self.repo)
        self.assertEqual(result["version"], f"{version.VERSION}+g{'a' * 12}.unknown")
        self.assertIsNone(result["dirty"])

    def test_ambient_git_environment_does_not_select_another_checkout(self):
        expected = version.build_info(self.repo)
        with patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_WORK_TREE": "/nonexistent"}):
            self.assertEqual(version.build_info(self.repo), expected)

    def test_api_requires_auth_is_uncached_and_frozen_until_new_app(self):
        outputs = self.root / "outputs"
        outputs.mkdir()
        with patch.object(dashboard, "PROJECT_DIR", self.repo):
            app = dashboard.create_app(outputs, token="fixture", remote_nodes_enabled=False)
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/version").status_code, 401)
                response = client.get("/api/version", headers={"Authorization": "Bearer fixture"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")
                first = response.json()
                self.assertEqual(app.version, first["version"])
                self.git("commit", "--allow-empty", "-m", "not yet running")
                with patch.object(dashboard, "build_info", side_effect=AssertionError("Do not reread Git on requests")):
                    self.assertEqual(client.get("/api/version").json(), first)
            restarted = dashboard.create_app(outputs, token="fixture", remote_nodes_enabled=False)
            with TestClient(restarted) as client:
                second = client.get("/api/version", headers={"Authorization": "Bearer fixture"}).json()
                self.assertNotEqual(first["version"], second["version"])
                self.assertEqual(second["commit"], self.git("rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
