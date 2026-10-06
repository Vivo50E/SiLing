"""Manual filing must never become process control or directory-wide deletion."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, json_store
from agent_orchestrator.session_archives import SessionArchives, ArchiveConflict


class SessionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.store = SessionArchives(self.root)

    def test_individual_records_persist_without_native_identity_aliases(self):
        source = self.root / "shared.json"
        source.write_text('{"resume_id":"same-native","linked_folders":["fixture"],"panel_state":"p0"}')
        before = source.read_bytes()
        self.store.change("same-run::task-a", True, 0)
        view = SessionArchives(self.root).read()
        self.assertTrue(view["entries"]["same-run::task-a"]["archived"])
        self.assertNotIn("same-run::task-b", view["entries"])
        self.assertNotIn("new-execution::task-a", view["entries"])
        self.assertEqual(source.read_bytes(), before)

    def test_idempotence_and_stale_conflict_preserve_revision_and_time(self):
        first = self.store.change("run::task", True, 0)
        self.assertEqual(self.store.change("run::task", True, 0), first)
        self.assertEqual(self.store.change("run::task", True, 1), first)
        with self.assertRaises(ArchiveConflict):
            self.store.change("run::task", False, 0)
        self.assertEqual(self.store.read(), first)
        second = self.store.change("run::task", False, 1)
        self.assertFalse(second["entries"]["run::task"]["archived"])
        with self.assertRaises(ArchiveConflict):
            self.store.change("run::task", True, 0)
        self.assertEqual(self.store.change("run::task", False, 1), second)

    def test_parallel_changes_preserve_other_sessions(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.store.change(f"run::{i}", True, 0), range(16)))
        self.assertEqual(len(self.store.read()["entries"]), 16)
        self.assertEqual(self.store.read()["revision"], 16)

    def test_corrupt_storage_is_not_reset(self):
        for text in ['{bad', '[]', '{"version":2}', '{"version":1,"revision":0,"entries":{"a":{}}}']:
            self.store.path.write_text(text)
            with self.assertRaises((ValueError, TypeError)):
                self.store.change("run::task", True, 0)
            self.assertEqual(self.store.path.read_text(), text)

    def test_failed_atomic_write_preserves_previous_state(self):
        before = self.store.change("run::a", True, 0)
        with patch.object(json_store, "_write_unlocked", side_effect=OSError("private path")):
            with self.assertRaises(OSError):
                self.store.change("run::b", True, 0)
        self.assertEqual(self.store.read(), before)

    def test_invalid_timestamps_fail_closed_without_overwriting(self):
        for timestamp in [float("nan"), float("inf"), -1, 10 ** 400, True]:
            text = json.dumps({"version":1, "revision":1, "entries":{
                "run::task":{"archived":True, "revision":1, "archived_at":timestamp}}})
            self.store.path.write_text(text)
            with self.assertRaises(ValueError):
                self.store.read()
            with self.assertRaises(ValueError):
                self.store.change("run::task", False, 1)
            self.assertEqual(self.store.path.read_text(), text)

    def app(self):
        app = dashboard.create_app(self.root, token="fixture", remote_nodes_enabled=False)
        self.row = {"run_id":"run::task", "kind":"task", "agent":"codex", "alive":True,
                    "resume_id":"native-id", "panel_state":"p0", "run_dir":str(self.root)}
        snapshot = {"sessions":[self.row], "ready":True, "scanning":False,
                    "updated_at":0, "age_s":0, "scan_duration_s":0, "error":""}
        self.stack.enter_context(patch.object(app.state.session_snapshots, "snapshot", return_value=snapshot))
        self.stack.enter_context(patch.object(app.state.session_snapshots, "request_refresh"))
        return app

    def client(self, app):
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_authenticated_api_two_clients_and_restart_do_not_control_sessions(self):
        app = self.app()
        first, second = self.client(app), self.client(app)
        headers = {"Authorization":"Bearer fixture"}
        payload = {"run_id":"run::task", "archived":True, "expected_revision":0}
        with patch.object(dashboard, "_lookup_run_light", return_value=self.row) as lookup, \
                patch.object(dashboard, "tmux_alive", side_effect=AssertionError("must not probe/control")):
            self.assertEqual(first.post("/api/session-archives", json=payload).status_code, 401)
            lookup.assert_not_called()
            self.assertEqual(first.post("/api/session-archives", json=payload, headers=headers).status_code, 200)
            view = second.get("/api/sessions", headers=headers).json()
            self.assertTrue(view["session_archives"]["entries"]["run::task"]["archived"])
            self.assertTrue(view["sessions"][0]["alive"])
            self.assertEqual(view["sessions"][0]["panel_state"], "p0")
            self.assertEqual(first.post("/api/session-archives", json=dict(payload, archived=False), headers=headers).status_code, 409)
        restarted = self.client(self.app()).get("/api/sessions", headers=headers).json()
        self.assertTrue(restarted["session_archives"]["entries"]["run::task"]["archived"])

    def test_invalid_missing_and_unsupported_requests_are_read_only(self):
        client = self.client(self.app())
        headers = {"Authorization":"Bearer fixture"}
        payload = {"run_id":"run::task", "archived":True, "expected_revision":0}
        for key, value in [("run_id", None), ("archived", "yes"), ("expected_revision", True), ("expected_revision", -1)]:
            self.assertEqual(client.post("/api/session-archives", json=dict(payload, **{key:value}), headers=headers).status_code, 400)
        with patch.object(dashboard, "_lookup_run_light") as lookup:
            for rid in [dashboard.qualify_run_id("offline", "run::task"), "tmux::temporary"]:
                self.assertEqual(client.post("/api/session-archives", json=dict(payload, run_id=rid), headers=headers).status_code, 409)
            lookup.assert_not_called()
        with patch.object(dashboard, "_lookup_run_light", return_value=None):
            self.assertEqual(client.post("/api/session-archives", json=payload, headers=headers).status_code, 404)
        self.assertFalse(self.store.path.exists())

    def test_storage_error_is_explicit_and_does_not_break_session_inventory(self):
        client = self.client(self.app())
        self.store.path.write_text("{corrupt")
        headers = {"Authorization":"Bearer fixture"}
        data = client.get("/api/sessions", headers=headers).json()
        self.assertIn("error", data["session_archives"])
        self.assertEqual(data["sessions"][0]["run_id"], "run::task")
        with patch.object(dashboard, "_lookup_run_light", return_value=self.row):
            response = client.post("/api/session-archives", json={"run_id":"run::task", "archived":True, "expected_revision":0}, headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.root), response.text)
        self.assertEqual(self.store.path.read_text(), "{corrupt")

    def test_old_active_snapshot_cannot_restart_archived_execution(self):
        client = self.client(self.app())
        self.store.change("run::task", True, 0)
        with patch.object(dashboard, "_load_active_snapshot", return_value={"sessions":[{
                "source_run_id":"run::task", "agent":"codex", "resume_id":"saved-id"}]}), \
                patch.object(dashboard, "_discover_runs", return_value=[]), \
                patch.object(dashboard, "_resolve_session_cwd", side_effect=AssertionError("must not spawn")):
            result = client.post("/api/active-snapshot/restore", json={}, headers={"Authorization":"Bearer fixture"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["restored_count"], 0)
        self.assertEqual(result.json()["skipped"][0]["reason"], "archived")
