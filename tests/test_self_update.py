import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.assertIn('confirmation: "APPROVE"', self.index)

    def test_apply_requires_verification_token_and_requests_restart(self):
        self.assertIn('api("/api/self-update/verify"', self.index)
        self.assertIn('"X-Orch-Self-Update": "reviewed"', self.index)
        self.assertIn('verification_token: selfUpdateVerification.verification_token', self.index)
        self.assertIn('restart: true', self.index)
        self.assertIn('@app.post("/api/self-update/apply")', self.backend)
        self.assertIn('explicit self-update intent is required', self.backend)
        self.assertIn('app.state.schedule_restart()', self.backend)


if __name__ == "__main__":
    unittest.main()
