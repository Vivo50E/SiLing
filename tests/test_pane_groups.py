"""Project groups persist independently from priorities, slots and agent processes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard
from agent_orchestrator.pane_groups import COLORS, PaneGroups


class PaneGroupTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.store = PaneGroups(self.root)
        self.row = {"run_id": "run::task", "agent": "claude", "resume_id": "native-1",
                    "panel_state": "p0", "alive": True}

    def create(self, name="Project A"):
        self.store.change({"action": "create", "name": name, "color": "teal"})
        return self.store.view([])["groups"][-1]["id"]

    def assign(self, gid, rows=None):
        self.store.change({"action": "assign", "group_id": gid}, rows or [self.row])

    def test_crud_round_trip_preserves_session_state(self):
        gid = self.create()
        self.assign(gid)
        reopened = PaneGroups(self.root)
        self.assertEqual(reopened.view([self.row])["members"]["run::task"], gid)
        self.store.change({"action": "update", "group_id": gid, "name": "新项目", "color": "purple"})
        self.assertEqual(reopened.view([])["groups"][0]["name"], "新项目")
        self.store.change({"action": "delete", "group_id": gid})
        self.assertEqual(reopened.view([self.row]), {"groups": [], "members": {"run::task": ""}})
        self.assertEqual(self.row["panel_state"], "p0")
        self.assertTrue(self.row["alive"])

    def test_custom_color_round_trip_keeps_legacy_fallback_and_membership(self):
        gid = self.create()
        self.assign(gid)
        self.store.change({"action": "update", "group_id": gid, "name": "Project A", "color": "#12AbEf"})
        raw = json.loads(self.store.path.read_text())
        self.assertEqual(raw["version"], 1)
        self.assertIn(raw["groups"][gid]["color"], COLORS)
        self.assertEqual(raw["groups"][gid]["custom_color"], "#12abef")
        reopened = PaneGroups(self.root).view([self.row])
        self.assertEqual(reopened["groups"][0]["color"], "#12abef")
        self.assertEqual(reopened["members"][self.row["run_id"]], gid)
        self.store.change({"action": "update", "group_id": gid, "name": "Project A", "color": "pink"})
        self.assertNotIn("custom_color", self.store.read()["groups"][gid])
        self.assertEqual(self.store.view([])["groups"][0]["color"], "pink")

    def test_legacy_colors_are_read_without_rewriting_metadata(self):
        for color in COLORS:
            self.store.change({"action": "create", "name": color, "color": color})
        before = self.store.path.read_bytes()
        self.assertEqual([g["color"] for g in self.store.view([])["groups"]], list(COLORS))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_custom_color_rejects_css_and_malformed_values_without_writing(self):
        self.create()
        before = self.store.path.read_bytes()
        for color in [None, [], {}, "#fff", "#ffffffff", "#12345g", "#123456;display:none", "url(evil)", "#123456\n"]:
            with self.subTest(color=color), self.assertRaises(ValueError):
                self.store.change({"action": "create", "name": "Custom", "color": color})
            self.assertEqual(self.store.path.read_bytes(), before)

    def test_invalid_stored_custom_color_is_not_silently_overwritten(self):
        gid = self.create()
        data = self.store.read()
        data["groups"][gid]["custom_color"] = "red;background:url(evil)"
        self.store.path.write_text(json.dumps(data))
        before = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.change({"action": "update", "group_id": gid, "name": "Project A", "color": "blue"})
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_resume_restart_and_nodes_use_conversation_identity(self):
        gid = self.create()
        self.assign(gid)
        restored = dict(self.row, run_id="new-run::task")
        remote = dict(restored, run_id="remote", node_id="other-host")
        codex = dict(restored, run_id="codex-run", agent="codex")
        members = self.store.view([restored, remote, codex])["members"]
        self.assertEqual(members, {"new-run::task": gid, "remote": "", "codex-run": ""})
        self.assign("", [restored])
        self.assertEqual(self.store.view([self.row])["members"][self.row["run_id"]], "")

    def test_late_native_identity_and_delete_never_resurrect_old_group(self):
        gid = self.create()
        old = dict(self.row, resume_id="")
        self.assign(gid, [old])
        self.store.view([self.row])  # the background scanner has discovered its ID
        restored = dict(self.row, run_id="restored")
        self.assertEqual(self.store.view([restored])["members"]["restored"], gid)
        other = self.create("Project B")
        self.assign(other, [restored])
        self.store.change({"action": "delete", "group_id": other})
        self.assertEqual(self.store.view([self.row, restored])["members"], {"run::task": "", "restored": ""})

    def test_terminal_membership_uses_run_not_slot_or_directory(self):
        gid = self.create()
        rows = [{"run_id": "shell-1", "agent": "terminal", "cwd": "/same"},
                {"run_id": "shell-2", "agent": "terminal", "cwd": "/same"}]
        self.assign(gid, [rows[0]])
        self.assertEqual(self.store.view(rows[::-1])["members"], {"shell-2": "", "shell-1": gid})

    def test_invalid_input_does_not_modify_storage(self):
        gid = self.create()
        before = self.store.path.read_bytes()
        for body in [
            {"action": "create", "name": "  ", "color": "blue"},
            {"action": "create", "name": "x" * 65, "color": "blue"},
            {"action": "create", "name": "bad\nname", "color": "blue"},
            {"action": "create", "name": "project a", "color": "blue", "group_id": gid},
            {"action": "create", "name": "valid", "color": "url(evil)"},
            {"action": "assign", "group_id": "missing"},
            {"action": "delete", "group_id": []},
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.store.change(body)
            self.assertEqual(self.store.path.read_bytes(), before)

    def test_parallel_edits_keep_unrelated_assignments(self):
        gid = self.create()
        rows = [{"run_id": f"r{i}"} for i in range(12)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda row: self.assign(gid, [row]), rows))
        self.assertEqual(set(self.store.view(rows)["members"].values()), {gid})

    def test_corrupt_storage_is_preserved(self):
        for value in ['{broken', '[]', '{"version":99}', '{"version":1,"groups":{},"members":{"x":[]}}']:
            self.store.path.write_text(value)
            with self.assertRaises(ValueError):
                self.store.change({"action":"create", "name":"A", "color":"blue"})
            self.assertEqual(self.store.path.read_text(), value)

    def test_stale_edits_cannot_recreate_deleted_groups(self):
        gid = self.create()
        self.assign(gid)
        self.store.change({"action":"delete", "group_id":gid})
        for body in [
            {"action":"update", "group_id":gid, "name":"stale", "color":"blue"},
            {"action":"assign", "group_id":gid},
        ]:
            with self.assertRaises(ValueError):
                self.store.change(body, [self.row])
        self.assertEqual(self.store.view([])["groups"], [])

    def test_authenticated_api_atomic_assignment_and_cross_client_visibility(self):
        self.stack.enter_context(patch.dict(os.environ, {
            "ORCH_DASHBOARD_CONFIG": str(self.root / "absent.json"),
            "ORCH_ACTIVE_SNAPSHOT_AUTOSAVE": "0",
        }))
        app = dashboard.create_app(self.root, token="secret", remote_nodes_enabled=False)
        client = TestClient(app)
        self.addCleanup(client.close)
        headers = {"Authorization": "Bearer secret"}
        snapshot = {"sessions":[self.row], "ready":True, "scanning":False,
                    "updated_at":0, "age_s":0, "scan_duration_s":0, "error":""}
        self.stack.enter_context(patch.object(app.state.session_snapshots, "snapshot", return_value=snapshot))
        self.stack.enter_context(patch.object(app.state.session_snapshots, "request_refresh"))
        self.stack.enter_context(patch.object(dashboard, "_lookup_run_light", side_effect=lambda _, rid: self.row if rid == self.row["run_id"] else None))
        create = {"action":"create", "name":"A", "color":"#123abc"}
        self.assertEqual(client.post("/api/pane-groups", json=create).status_code, 401)
        self.assertEqual(client.post("/api/pane-groups", json=create, headers=headers).status_code, 200)
        gid = client.get("/api/sessions", headers=headers).json()["pane_groups"]["groups"][0]["id"]
        payload = {"action":"assign", "group_id":gid, "run_ids":["run::task", "missing"]}
        self.assertEqual(client.post("/api/pane-groups", json=payload, headers=headers).status_code, 404)
        self.assertEqual(self.store.view([self.row])["members"]["run::task"], "")
        payload["run_ids"] = ["run::task"]
        self.assertEqual(client.post("/api/pane-groups", json=payload, headers=headers).status_code, 200)
        second = TestClient(app)  # No context manager: do not start background services.
        self.addCleanup(second.close)
        data = second.get("/api/sessions", headers=headers).json()
        self.assertEqual(data["pane_groups"]["groups"][0]["color"], "#123abc")
        self.assertEqual(data["pane_groups"]["members"]["run::task"], gid)
        self.assertEqual(data["sessions"][0]["panel_state"], "p0")
        for ids in [None, [], [False], ["run::task"] * 501]:
            payload["run_ids"] = ids
            self.assertEqual(client.post("/api/pane-groups", json=payload, headers=headers).status_code, 400)
        # Remote membership belongs to this Dashboard; no write to the node is needed.
        remote_id = dashboard.qualify_run_id("dev", "remote::task")
        remote_row = dict(self.row, run_id=remote_id, node_id="dev")
        with patch.object(app.state.remote_nodes, "sessions", return_value=[remote_row]):
            payload["run_ids"] = [remote_id]
            self.assertEqual(client.post("/api/pane-groups", json=payload, headers=headers).status_code, 200)
            self.assertEqual(client.get("/api/sessions", headers=headers).json()["pane_groups"]["members"][remote_id], gid)
        self.store.path.write_text("{broken")
        self.assertEqual(client.post("/api/pane-groups", json=create, headers=headers).status_code, 503)
        data = client.get("/api/sessions", headers=headers).json()
        self.assertTrue(data["pane_groups"]["error"])
        self.assertEqual(data["sessions"][0]["run_id"], "run::task")


if __name__ == "__main__":
    unittest.main()
