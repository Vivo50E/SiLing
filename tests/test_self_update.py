import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_orchestrator.self_update import SelfUpdateError, SelfUpdateManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


class SelfUpdateManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.candidate = self.root / "candidate"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.name", "Self Update Test")
        _git(self.repo, "config", "user.email", "self-update@example.invalid")
        (self.repo / "app.txt").write_text("base\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_smoke.py").write_text(
            "import unittest\n\n"
            "class SmokeTest(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        _git(self.repo, "add", "app.txt", "tests/test_smoke.py")
        _git(self.repo, "commit", "-m", "base")
        _git(
            self.repo, "worktree", "add", str(self.candidate),
            "-b", "agent/self-improve-test",
        )
        (self.candidate / "app.txt").write_text("improved\n")
        _git(self.candidate, "add", "app.txt")
        _git(self.candidate, "commit", "-m", "improve app")
        self.manager = SelfUpdateManager(self.repo, python=sys.executable)

    def tearDown(self):
        self.temp.cleanup()

    def _publish_upstream_commit(self) -> str:
        bare = self.root / "remote.git"
        publisher = self.root / "publisher"
        _git(self.root, "init", "--bare", "-b", "main", str(bare))
        _git(self.repo, "remote", "add", "origin", str(bare))
        _git(self.repo, "push", "-u", "origin", "main")
        _git(self.root, "clone", str(bare), str(publisher))
        _git(publisher, "config", "user.name", "Upstream Publisher")
        _git(publisher, "config", "user.email", "upstream@example.invalid")
        (publisher / "upstream.txt").write_text("new upstream code\n")
        _git(publisher, "add", "upstream.txt")
        _git(publisher, "commit", "-m", "publish upstream update")
        _git(publisher, "push", "origin", "main")
        return _git(publisher, "rev-parse", "HEAD")

    def test_status_lists_only_committed_fast_forward_candidate(self):
        status = self.manager.status()

        self.assertTrue(status["available"])
        self.assertEqual(status["target_branch"], "main")
        self.assertEqual(len(status["candidates"]), 1)
        candidate = status["candidates"][0]
        self.assertTrue(candidate["eligible"])
        self.assertEqual(candidate["ahead"], 1)
        self.assertEqual(candidate["behind"], 0)
        self.assertEqual(candidate["files"], [{"status": "M", "path": "app.txt"}])
        self.assertEqual(candidate["commits"][0]["subject"], "improve app")

    def test_dirty_candidate_is_never_eligible(self):
        (self.candidate / "unreviewed.txt").write_text("not committed\n")

        candidate = self.manager.status()["candidates"][0]

        self.assertFalse(candidate["eligible"])
        self.assertIn("uncommitted", candidate["blocked_reason"])

    def test_verify_runs_suite_and_returns_commit_bound_token(self):
        result = self.manager.verify("agent/self-improve-test")

        self.assertTrue(result["ok"])
        self.assertEqual(result["test_count"], 1)
        self.assertTrue(result["verification_token"])
        self.assertEqual(
            result["candidate_head"], _git(self.candidate, "rev-parse", "HEAD")
        )

    def test_verification_children_use_runtime_venv_not_system_python(self):
        # A detached checkout has no .venv. Its executable Python scripts must
        # still inherit the verifier's dependencies rather than the host PATH.
        runtime = self.root / "runtime"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(runtime)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        python = runtime / "bin" / "python"
        site = subprocess.run(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        Path(site, "siling_verification_probe.py").write_text("VALUE = 'runtime dependency'\n")
        wrong_bin = self.root / "wrong-bin"
        wrong_bin.mkdir()
        wrong_python = wrong_bin / "python3"
        wrong_python.write_text("#!/bin/sh\necho wrong-python >&2\nexit 91\n")
        wrong_python.chmod(0o755)
        probe = self.candidate / "probe"
        probe.write_text(
            "#!/usr/bin/env python3\n"
            "from siling_verification_probe import VALUE\n"
            "print(VALUE)\n"
        )
        probe.chmod(0o755)
        (self.candidate / "tests" / "test_child.py").write_text(
            "import os, subprocess, unittest\n"
            "class ChildTest(unittest.TestCase):\n"
            "    def test_child(self):\n"
            "        self.assertEqual(os.environ['SILING_VERIFY_PROBE'], 'inherited')\n"
            "        for command in (['./probe'], ['python3', './probe']):\n"
            "            result = subprocess.run(command, capture_output=True, text=True)\n"
            "            self.assertEqual(result.returncode, 0, result.stderr)\n"
            "            self.assertEqual(result.stdout.strip(), 'runtime dependency')\n"
        )
        _git(self.candidate, "add", "probe", "tests/test_child.py")
        _git(self.candidate, "commit", "-m", "test verification child interpreter")
        _git(self.repo, "remote", "add", "origin", str(self.root / "unused.git"))
        _git(self.repo, "update-ref", "refs/remotes/origin/main",
             _git(self.candidate, "rev-parse", "HEAD"))
        original_path = str(wrong_bin) + os.pathsep + os.environ.get("PATH", os.defpath)
        with patch.dict(os.environ, {"PATH": original_path, "SILING_VERIFY_PROBE": "inherited"}):
            manager = SelfUpdateManager(self.repo, python=str(python))
            for branch in ("agent/self-improve-test", "upstream:origin/main"):
                with self.subTest(branch=branch):
                    result = manager.verify(branch)
                    self.assertTrue(result["ok"], result["output"])
                    self.assertEqual(result["test_count"], 2)
                    self.assertIn("verification_token", result)
                    self.assertEqual(os.environ["PATH"], original_path)

    def test_verification_resolves_named_python_without_resolving_venv_symlinks(self):
        runtime_bin = Path(sys.executable).absolute().parent
        with patch.dict(os.environ, {"PATH": str(runtime_bin) + os.pathsep + os.defpath}):
            manager = SelfUpdateManager(self.repo, python="python3")
            environment = manager._verification_environment()
        self.assertEqual(environment["PATH"].split(os.pathsep)[0], str(runtime_bin))

    def test_apply_requires_exact_confirmation_and_verified_commits(self):
        candidate = self.manager._candidate("agent/self-improve-test")
        token = "verified-token"
        self.manager._verified[token] = {
            "branch": candidate["branch"],
            "fingerprint": self.manager._fingerprint(candidate),
            "expires_at": 32503680000,
        }
        with self.assertRaisesRegex(SelfUpdateError, "APPROVE"):
            self.manager.apply(candidate["branch"], token, "approve")

        result = self.manager.apply(candidate["branch"], token, "APPROVE")

        self.assertTrue(result["ok"])
        self.assertEqual(_git(self.repo, "rev-parse", "HEAD"), candidate["head"])
        self.assertEqual((self.repo / "app.txt").read_text(), "improved\n")

    def test_candidate_change_invalidates_verification(self):
        candidate = self.manager._candidate("agent/self-improve-test")
        token = "verified-token"
        self.manager._verified[token] = {
            "branch": candidate["branch"],
            "fingerprint": self.manager._fingerprint(candidate),
            "expires_at": 32503680000,
        }
        (self.candidate / "second.txt").write_text("second\n")
        _git(self.candidate, "add", "second.txt")
        _git(self.candidate, "commit", "-m", "change after tests")

        with self.assertRaisesRegex(SelfUpdateError, "changed after verification"):
            self.manager.apply(candidate["branch"], token, "APPROVE")

    def test_fetch_verify_and_apply_upstream_fast_forward(self):
        upstream_head = self._publish_upstream_commit()

        fetched = self.manager.fetch_upstream()
        status = self.manager.status()
        upstream = next(
            item for item in status["candidates"]
            if item.get("kind") == "upstream"
        )

        self.assertTrue(fetched["ok"])
        self.assertEqual(fetched["remote"], "origin")
        self.assertEqual(upstream["branch"], "upstream:origin/main")
        self.assertEqual(upstream["head"], upstream_head)
        self.assertEqual(upstream["ahead"], 1)
        self.assertTrue(upstream["eligible"])

        verification = self.manager.verify(upstream["branch"])
        self.assertTrue(verification["ok"], verification["output"])
        self.assertEqual(verification["test_count"], 1)

        result = self.manager.apply(
            upstream["branch"], verification["verification_token"], "APPROVE",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(_git(self.repo, "rev-parse", "HEAD"), upstream_head)
        self.assertEqual((self.repo / "upstream.txt").read_text(), "new upstream code\n")

    def test_same_agent_and_upstream_commit_is_counted_once_as_upstream(self):
        upstream_head = self._publish_upstream_commit()
        self.manager.fetch_upstream()
        _git(self.candidate, "reset", "--hard", upstream_head)

        matching = [
            item for item in self.manager.status()["candidates"]
            if item.get("head") == upstream_head
        ]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["kind"], "upstream")

    def test_status_ignores_ancestor_refs_after_local_branch_moves_ahead(self):
        bare = self.root / "remote.git"
        _git(self.root, "init", "--bare", "-b", "main", str(bare))
        _git(self.repo, "remote", "add", "origin", str(bare))
        _git(self.repo, "push", "-u", "origin", "main")
        _git(self.candidate, "reset", "--hard", "main")
        (self.repo / "local.txt").write_text("local fix\n")
        _git(self.repo, "add", "local.txt")
        _git(self.repo, "commit", "-m", "local fix after upstream")

        status = self.manager.status()

        self.assertEqual(status["candidates"], [])


class SelfUpdateDashboardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = Path(__file__).resolve().parents[1]
        cls.index = (cls.project / "static" / "index.html").read_text()
        cls.backend = (
            cls.project / "agent_orchestrator" / "dashboard.py"
        ).read_text()

    def test_dashboard_uses_inline_two_click_verify_and_apply_control(self):
        self.assertIn('id="btn-self-update"', self.index)
        self.assertNotIn('id="self-update-modal"', self.index)
        self.assertNotIn('typed !== "APPROVE"', self.index)
        self.assertIn('button.textContent = "approve update"', self.index)
        self.assertIn('button.textContent = pending.length ? "update blocked"', self.index)
        self.assertIn('confirmation: "APPROVE"', self.index)

    def test_apply_requires_verification_token_and_requests_restart(self):
        self.assertIn('api("/api/self-update/fetch"', self.index)
        self.assertIn('@app.post("/api/self-update/fetch")', self.backend)
        self.assertIn('candidate?.kind === "upstream"', self.index)
        self.assertIn('api("/api/self-update/verify"', self.index)
        self.assertIn('"X-Orch-Self-Update": "reviewed"', self.index)
        self.assertIn('verification_token: selfUpdateVerification.verification_token', self.index)
        self.assertIn('restart: true', self.index)
        self.assertIn('@app.post("/api/self-update/apply")', self.backend)
        self.assertIn('explicit self-update intent is required', self.backend)
        self.assertIn('app.state.schedule_restart()', self.backend)


if __name__ == "__main__":
    unittest.main()
