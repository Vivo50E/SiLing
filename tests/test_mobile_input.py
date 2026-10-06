"""Mobile input is explicit and never retried after an uncertain delivery."""
from contextlib import ExitStack
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard
from agent_orchestrator.session_archives import SessionArchives


class MobileInputTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.archives = SessionArchives(root)
        self.client = TestClient(dashboard.create_app(root, token="fixture", remote_nodes_enabled=False))
        self.addCleanup(self.client.close)
        self.headers = {"Authorization":"Bearer fixture"}
        self.row = {"tmux_session":"fixture", "alive":True, "agent":"codex"}
        self.lookup = self.stack.enter_context(patch.object(dashboard, "_lookup_run", return_value=self.row))
        self.stack.enter_context(patch.object(dashboard, "tmux_alive", return_value=True))
        self.send = self.stack.enter_context(patch.object(dashboard, "tmux_send", return_value=(True, "")))

    def post(self, data):
        return self.client.post("/api/sessions/fixture/input", json=data, headers=self.headers)

    def test_authentication_precedes_lookup_and_delivery(self):
        self.assertEqual(self.client.post("/api/sessions/fixture/input", json={"text":"hello"}).status_code, 401)
        self.lookup.assert_not_called()
        self.send.assert_not_called()

    def test_multiline_is_exact_and_accepted_is_not_execution(self):
        text = "  第一行\nsecond 😀\n"
        response = self.post({"text":text})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"ok":True,"delivery":"accepted"})
        self.send.assert_called_once_with("fixture", text, literal=True, enter=True, retries=0)

    def test_only_explicit_supported_keys_are_forwarded(self):
        for key in ("Escape", "Tab", "C-c"):
            self.send.reset_mock()
            self.assertEqual(self.post({"key":key}).status_code, 200)
            self.send.assert_called_once_with("fixture", key, literal=False, enter=False, retries=0)
        for value in ({"key":"Enter"}, {"key":"kill-session"}, {"key":3}, {"key":"Tab","text":"oops"}):
            self.assertEqual(self.post(value).status_code, 400)

    def test_invalid_and_oversized_input_never_reaches_tmux(self):
        for value in ({}, {"text":3}, {"text":""}, {"text":"a\0b"}, {"text":"x"*8001},
                      {"text":"hello","enter":False}, [], None):
            self.assertEqual(self.post(value).status_code, 400)
        response = self.client.post("/api/sessions/fixture/input", content=b"x"*65537, headers=self.headers)
        self.assertEqual(response.status_code, 413)
        response = self.client.post("/api/sessions/fixture/input", content=b"{bad", headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.send.assert_not_called()

    def test_missing_ended_and_archived_targets_do_not_receive_input(self):
        self.lookup.return_value = None
        self.assertEqual(self.post({"text":"hello"}).status_code, 404)
        self.lookup.return_value = dict(self.row, agent_exited=True)
        self.assertEqual(self.post({"text":"hello"}).status_code, 409)
        self.lookup.return_value = self.row
        with patch.object(dashboard, "tmux_alive", return_value=False):
            self.assertEqual(self.post({"text":"hello"}).status_code, 409)
        self.archives.change("fixture", True, 0)
        self.assertEqual(self.post({"text":"hello"}).status_code, 409)
        self.send.assert_not_called()

    def test_uncertain_transport_result_is_sanitized_without_repeat(self):
        self.send.return_value = (False, "private output must not escape")
        response = self.post({"text":"hello"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private output", response.text)
        self.assertIn("not confirmed", response.text)
        self.send.assert_called_once()


class OneShotTmuxTests(unittest.TestCase):
    def test_timeout_does_not_retry_or_send_enter(self):
        with patch.object(dashboard, "_tmux_target_pane", return_value=("%42", "")), \
                patch.object(dashboard.subprocess, "run", side_effect=subprocess.TimeoutExpired("tmux", 10)) as run:
            ok, _ = dashboard.tmux_send("fixture", "exact text", enter=True, retries=0)
        self.assertFalse(ok)
        self.assertEqual(run.call_count, 1)

    def test_enter_failure_never_replays_pasted_text(self):
        with patch.object(dashboard, "_tmux_target_pane", return_value=("%42", "")), \
                patch.object(dashboard, "_tmux_send_keys", side_effect=[(True, ""), (False, "timeout")]) as send:
            ok, _ = dashboard.tmux_send("fixture", "exact text", enter=True, retries=0)
        self.assertFalse(ok)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].kwargs, {"retries":0})
        self.assertEqual(send.call_args_list[1].kwargs, {"retries":0,"timeout":5})
