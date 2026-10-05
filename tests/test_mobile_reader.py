"""Additive snapshot evidence for the mobile reader; never control sessions."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class MobileReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = {"tmux_session": "fixture", "run_dir": str(self.root),
                    "log_file": "output.log"}
        self.app = dashboard.create_app(self.root, ttyd_enabled=False,
                                        remote_nodes_enabled=False)

    def read(self, text, params=None, alive=True):
        with patch.object(dashboard, "_lookup_run_light", return_value=self.run), \
                patch.object(dashboard, "tmux_alive", return_value=alive), \
                patch.object(dashboard, "tmux_capture_lines", return_value=text) as capture, \
                TestClient(self.app) as client:
            response = client.get("/api/sessions/fixture/read", params=params or {
                "lines": 2, "max_chars": 100,
            })
        return response, capture

    def test_tail_metadata_and_one_extra_line_probe(self):
        before = time.time()
        response, capture = self.read("first\nsecond\nthird\n")
        data = response.json()
        self.assertEqual(data["text"], "second\nthird\n")
        self.assertTrue(data["truncated"])
        self.assertEqual(data["truncation_reasons"], ["lines"])
        self.assertGreaterEqual(data["observed_at"], before)
        self.assertIsNone(data["content_updated_at"])
        capture.assert_called_once_with("fixture", 3, "tail")

    def test_exact_limit_empty_and_unavailable_are_distinct(self):
        for text in ("one\ntwo\n", ""):
            data = self.read(text)[0].json()
            self.assertTrue(data["ok"])
            self.assertFalse(data["truncated"])
        data = self.read(None)[0].json()
        self.assertFalse(data["ok"])
        self.assertIsNone(data["observed_at"])

    def test_character_cap_unicode_and_direction(self):
        for position, expected in (("head", "甲😀乙"), ("tail", "😀乙丙")):
            data = self.read("甲😀乙丙", {
                "lines": 2, "position": position, "max_chars": 3,
            })[0].json()
            self.assertEqual(data["text"], expected)
            self.assertEqual(data["truncation_reasons"], ["chars"])

    def test_capture_failure_uses_log_without_claiming_live_output(self):
        (self.root / "output.log").write_text("old\nnew\nlast\n")
        data = self.read(None)[0].json()
        self.assertEqual(data["source"], "log")
        self.assertTrue(data["alive"])
        self.assertIsNone(data["content_updated_at"])
        self.assertEqual(data["text"], "new\nlast\n")
        self.assertTrue(data["truncated"])

    def test_ended_log_head_and_legacy_request(self):
        (self.root / "output.log").write_text("one\ntwo\nthree\n")
        data = self.read(None, {"lines": 2, "position": "head", "max_chars": 100}, False)[0].json()
        self.assertEqual(data["text"], "one\ntwo\n")
        self.assertFalse(data["alive"])
        response, capture = self.read("legacy\n", {"lines": 2})
        self.assertEqual(response.json()["text"], "legacy\n")
        capture.assert_called_once_with("fixture", 2, "tail")

    def test_invalid_bounds_and_missing_session(self):
        for value in (0, 200001, "bad"):
            self.assertEqual(self.read("", {"max_chars": value})[0].status_code, 422)
        self.run = None
        self.assertEqual(self.read("")[0].status_code, 404)

    def test_unreadable_log_does_not_claim_success(self):
        (self.root / "output.log").write_text("fixture")
        with patch.object(dashboard, "_read_file_lines", return_value=None):
            data = self.read(None, alive=False)[0].json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["source"], "none")
        self.assertIsNone(data["observed_at"])

    def test_read_requires_auth_before_lookup_or_capture(self):
        app = dashboard.create_app(self.root, token="fixture-secret",
                                   ttyd_enabled=False, remote_nodes_enabled=False)
        with patch.object(dashboard, "tmux_capture_lines") as capture, TestClient(app) as client:
            self.assertEqual(client.get("/api/sessions/fixture/read?max_chars=32000").status_code, 401)
        capture.assert_not_called()

    def test_orphan_tmux_read_uses_same_bounded_contract(self):
        with patch.object(dashboard, "tmux_alive", return_value=True), \
                patch.object(dashboard, "tmux_capture_lines", return_value="orphan\n"), \
                TestClient(self.app) as client:
            data = client.get("/api/sessions/tmux::orphan/read?max_chars=100").json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "tmux")
        self.assertFalse(data["truncated"])
