"""A launch directory preference must never inject commands into a process."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class WorkingDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.outputs = self.root / "outputs"
        self.run = self.outputs / "fixture"
        self.run.mkdir(parents=True)
        self.target = self.root / "project with spaces"
        self.target.mkdir()
        self.meta = self.run / "session.json"
        self.meta.write_text(json.dumps({"name": "shell", "agent": "terminal", "cwd": str(self.root), "label": "Keep", "resume_id": "native-original"}))
        self.stack.enter_context(patch.dict(os.environ, {"ORCH_ACTIVE_SNAPSHOT_AUTOSAVE": "0", "ORCH_DASHBOARD_CONFIG": str(self.root / "none")}))
        self.send = self.stack.enter_context(patch.object(dashboard, "tmux_send"))
        self.stop = self.stack.enter_context(patch.object(dashboard, "_graceful_stop_agent"))
        self.client = TestClient(dashboard.create_app(self.outputs, token="fixture-token", ttyd_enabled=False, remote_nodes_enabled=False))
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer fixture-token"}

    def save(self, body, headers=None):
        return self.client.post("/api/sessions/fixture::shell/working-directory", json=body, headers=self.headers if headers is None else headers)

    def test_save_persists_separate_preference_and_preserves_identity(self):
        response = self.save({"cwd": str(self.target)})
        self.assertEqual(response.status_code, 200, response.text)
        stored = json.loads(self.meta.read_text())
        self.assertEqual(stored["launch_cwd"], str(self.target))
        self.assertEqual(stored["cwd"], str(self.root))
        self.assertEqual(stored["resume_id"], "native-original")
        self.assertEqual(dashboard._lookup_run_light(self.outputs, "fixture::shell")["launch_cwd"], str(self.target))
        self.send.assert_not_called()
        self.stop.assert_not_called()

    def test_invalid_paths_and_bodies_leave_metadata_unchanged(self):
        before = self.meta.read_bytes()
        for body in [[], {}, {"cwd": 1}, {"cwd": ""}, {"cwd": "relative"}, {"cwd": str(self.root / "missing")}, {"cwd": str(self.meta)}, {"cwd": "/tmp\ncommand"}]:
            with self.subTest(body=body):
                self.assertEqual(self.save(body).status_code, 400)
                self.assertEqual(self.meta.read_bytes(), before)
        self.send.assert_not_called()

    def test_authentication_required(self):
        self.assertEqual(self.save({"cwd": str(self.target)}, headers={}).status_code, 401)
        self.assertNotIn("launch_cwd", json.loads(self.meta.read_text()))

    def test_task_updates_only_requested_record(self):
        self.meta.unlink()
        state = self.run / "state.json"
        state.write_text(json.dumps({"shell": {"cwd": str(self.root)}, "other": {"cwd": "unchanged"}}))
        self.assertEqual(self.save({"cwd": str(self.target)}).status_code, 200)
        saved = json.loads(state.read_text())
        self.assertEqual(saved["shell"]["launch_cwd"], str(self.target))
        self.assertEqual(saved["other"], {"cwd": "unchanged"})
