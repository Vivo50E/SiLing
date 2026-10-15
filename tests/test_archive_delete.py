"""Permanent archive deletion only removes explicitly selected stopped local runs."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard
from agent_orchestrator.session_archives import SessionArchives


class ArchiveDeletionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.outputs = self.root / "outputs"
        self.folder = self.outputs / "run"
        self.folder.mkdir(parents=True)
        (self.folder / "session.json").write_text('{"task":"task"}')
        (self.folder / "log.txt").write_text("saved output")
        self.external = self.root / "source"
        self.external.mkdir()
        (self.external / "keep.txt").write_text("keep")
        (self.folder / "linked-files").symlink_to(self.external, target_is_directory=True)
        self.row = {"run_id":"run::task", "kind":"run", "alive":False,
                    "run_dir":str(self.folder), "tmux_session":"stopped", "agent":"codex"}
        self.rows = [self.row]
        self.store = SessionArchives(self.outputs)
        self.store.change("run::task", True, 0)
        app = dashboard.create_app(self.outputs, token="fixture", remote_nodes_enabled=False)
        self.client = self.stack.enter_context(TestClient(app))
        self.stack.enter_context(patch.object(dashboard, "_discover_runs", side_effect=lambda *a, **kw:self.rows))
        self.tmux = self.stack.enter_context(patch.object(dashboard, "tmux_alive", return_value=False))
        self.stack.enter_context(patch.object(app.state.session_snapshots, "request_refresh"))

    def delete(self, body=None, auth=True):
        return self.client.request("DELETE", "/api/session-archives/run::task",
            json=body if body is not None else {"confirm":True, "expected_revision":1},
            headers={"Authorization":"Bearer fixture"} if auth else {})

    def test_confirmed_delete_preserves_linked_sources_and_blocks_recovery(self):
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.folder.exists())
        self.assertEqual((self.external / "keep.txt").read_text(), "keep")
        self.assertTrue(response.json()["session_archives"]["entries"]["run::task"]["deleted"])
        # A duplicate request must not delete a newly created directory.
        self.folder.mkdir()
        self.assertEqual(self.delete().status_code, 200)
        self.assertTrue(self.folder.exists())
        with patch.object(dashboard, "_lookup_run_light", return_value=self.row):
            response = self.client.post("/api/session-archives", json={
                "run_id":"run::task", "archived":False, "expected_revision":2},
                headers={"Authorization":"Bearer fixture"})
        # The lookup must not permit a deleted execution to be unarchived.
        self.assertEqual(response.status_code, 409)
        with patch.object(dashboard, "_load_active_snapshot", return_value={"sessions":[{
                "source_run_id":"run::task", "agent":"codex", "resume_id":"saved"}]}), \
                patch.object(dashboard, "_resolve_session_cwd", side_effect=AssertionError("must not spawn")):
            restored = self.client.post("/api/active-snapshot/restore", json={},
                headers={"Authorization":"Bearer fixture"})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["restored_count"], 0)

    def test_missing_record_can_be_cleared_without_deleting_other_files(self):
        self.rows.clear()
        response = self.delete()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.folder.exists())
        self.assertTrue(self.store.read()["entries"]["run::task"]["deleted"])

    def test_confirmation_auth_and_stale_archive_state_are_required(self):
        self.assertEqual(self.delete(auth=False).status_code, 401)
        for body in [{}, {"confirm":False,"expected_revision":1},
                     {"confirm":True,"expected_revision":True}, {"confirm":True,"expected_revision":-1}]:
            self.assertEqual(self.delete(body).status_code, 400)
        self.assertEqual(self.delete({"confirm":True,"expected_revision":0}).status_code, 409)
        self.store.change("run::task", False, 1)
        self.assertEqual(self.delete().status_code, 409)
        self.assertTrue((self.folder / "log.txt").exists())

    def test_running_tmux_and_shared_folder_are_refused(self):
        self.row["alive"] = True
        self.assertEqual(self.delete().status_code, 409)
        self.row["alive"] = False
        self.tmux.return_value = True
        self.assertEqual(self.delete().status_code, 409)
        self.tmux.return_value = False
        self.rows.append(dict(self.row, run_id="run::other"))
        self.assertEqual(self.delete().status_code, 409)
        self.assertTrue((self.folder / "log.txt").exists())
        self.assertNotIn("deleted", self.store.read()["entries"]["run::task"])

    def test_unsafe_root_external_symlink_and_nested_paths_are_refused(self):
        symlink = self.outputs / "linked-run"
        symlink.symlink_to(self.external, target_is_directory=True)
        for folder in (self.outputs, self.external, symlink, self.folder / "nested"):
            with self.subTest(folder=folder):
                self.row["run_dir"] = str(folder)
                self.assertEqual(self.delete().status_code, 400)
        self.assertTrue(self.folder.exists())
        self.assertTrue((self.external / "keep.txt").exists())

    def test_corrupt_archive_and_filesystem_failure_do_not_hide_the_entry(self):
        before = self.store.path.read_bytes()
        self.store.path.write_text("{corrupt")
        self.assertEqual(self.delete().status_code, 503)
        self.assertTrue(self.folder.exists())
        self.store.path.write_bytes(before)
        with patch.object(dashboard.shutil, "rmtree", side_effect=OSError("private path")):
            response = self.delete()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.root), response.text)
        self.assertEqual(self.store.path.read_bytes(), before)
