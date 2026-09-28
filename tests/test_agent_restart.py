"""Restart is an explicit, resumable process replacement, never a force kill."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class AgentRestartTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.dict(os.environ, {
            "ORCH_ACTIVE_SNAPSHOT_AUTOSAVE": "0",
            "ORCH_DASHBOARD_CONFIG": str(self.root / "missing.json"),
        }))
        self.src = {"run_id": "source", "kind": "run", "alive": True,
                    "agent": "codex", "tmux_session": "orch-restart-fixture",
                    "resume_id": "conversation-123", "cwd": str(self.root),
                    "model": "fixture-model", "effort": "high",
                    "display_name": "Keep my name", "panel_state": "p1",
                    "terminal_theme": "light", "run_dir": str(self.root / "old")}
        self.alive = True
        self.lookup = self.stack.enter_context(patch.object(dashboard, "_lookup_run", side_effect=lambda *_: dict(self.src)))
        self.stack.enter_context(patch.object(dashboard, "tmux_alive", side_effect=lambda _: self.alive))
        self.stop = self.stack.enter_context(patch.object(dashboard, "_graceful_stop_agent", return_value={"ok": True}))
        self.kill = self.stack.enter_context(patch.object(dashboard, "tmux_kill", side_effect=self.kill_wrapper))
        self.shadow = self.stack.enter_context(patch.object(dashboard, "kill_shadow_session"))
        self.persist = self.stack.enter_context(patch.object(dashboard, "_persist_resume_metadata", return_value=True))
        self.discover = self.stack.enter_context(patch.object(dashboard, "_discover_resume_metadata"))
        self.stack.enter_context(patch.object(dashboard, "_schedule_native_resume_capture"))
        self.links = self.stack.enter_context(patch.object(dashboard, "_copy_linked_folders_to_spawned_run", return_value={"copied": 2}))
        self.ui = self.stack.enter_context(patch.object(dashboard, "_copy_snapshot_ui_metadata_to_spawned_run", return_value={"copied": True, "panel_state": "p1"}))
        app = dashboard.create_app(self.root / "outputs", token="fixture-token", ttyd_enabled=False, remote_nodes_enabled=False)
        # No lifespan: these focused route tests must not start inventory workers.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.spawn = self.stack.enter_context(patch.object(dashboard.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "Session: orch-new-fixture\n", "")))

    def kill_wrapper(self, session):
        self.alive = False
        return True

    def restart(self):
        return self.client.post("/api/sessions/source/restart", headers={"Authorization": "Bearer fixture-token"})

    def test_restart_requires_authentication(self):
        self.assertEqual(self.client.post("/api/sessions/source/restart").status_code, 401)
        self.stop.assert_not_called()

    def test_supported_agents_resume_exact_identity_and_copy_metadata(self):
        for agent in ("codex", "claude", "cursor"):
            with self.subTest(agent=agent):
                self.alive = True
                self.src["agent"] = agent
                result = self.restart()
                self.assertEqual(result.status_code, 200, result.text)
                data = result.json()
                self.assertTrue(data["ok"])
                self.assertEqual(data["resume_id"], "conversation-123")
                self.assertEqual(data["restarted_from"], "source")
                args = self.spawn.call_args.args[0]
                self.assertEqual(args[args.index("--resume-id") + 1], "conversation-123")
                self.assertEqual(args[args.index("--label") + 1], "Keep my name")
                self.assertEqual(args[args.index("--model") + 1], "fixture-model")
                self.assertIn(agent, args)
                self.assertEqual(args[-1], str(self.root))
                self.assertTrue(data["ui_metadata_copied"])
                self.assertEqual(data["linked_folders_copied"], 2)
                self.assertEqual(self.ui.call_args.args[1]["terminal_theme"], "light")
        self.discover.assert_not_called()

    def test_preflight_failure_never_stops_agent(self):
        for changes, code in [({"resume_id": ""}, 409), ({"agent": "terminal"}, 400),
                              ({"agent": "unknown"}, 400), ({"alive": False}, 409),
                              ({"cwd": ""}, 409), ({"cwd": str(self.root / "absent")}, 400),
                              ({"resume": {"agent": "claude"}}, 409)]:
            original = dict(self.src)
            with self.subTest(changes=changes):
                self.src.update(changes)
                self.assertEqual(self.restart().status_code, code)
                self.stop.assert_not_called()
                self.kill.assert_not_called()
                self.spawn.assert_not_called()
            self.src = original

    def test_missing_run_returns_404(self):
        self.lookup.side_effect = None
        self.lookup.return_value = None
        self.assertEqual(self.restart().status_code, 404)
        self.stop.assert_not_called()

    def test_failed_persistence_never_stops_agent(self):
        self.persist.return_value = False
        self.assertEqual(self.restart().status_code, 409)
        self.stop.assert_not_called()

    def test_exit_timeout_never_force_kills_or_launches(self):
        self.stop.return_value = {"ok": False, "reason": "still running"}
        result = self.restart().json()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stop")
        self.kill.assert_not_called()
        self.spawn.assert_not_called()

    def test_failed_wrapper_close_never_launches_duplicate(self):
        self.kill.side_effect = None
        self.kill.return_value = False
        self.assertFalse(self.restart().json()["ok"])
        self.spawn.assert_not_called()

    def test_failed_launch_reports_stopped_source_and_retains_resume(self):
        self.spawn.return_value = subprocess.CompletedProcess([], 1, "", "fixture launch failed")
        result = self.restart().json()
        self.assertEqual(result["stage"], "resume")
        self.assertFalse(result["ok"])
        self.assertIn("saved source", result["hint"])
        self.assertEqual(self.persist.call_args.args[1]["resume_id"], "conversation-123")
        self.assertEqual(self.persist.call_args.kwargs["status"], "stopped")

    def test_concurrent_restart_is_rejected_and_guard_is_released(self):
        entered, release = threading.Event(), threading.Event()
        def stop(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return {"ok": False, "reason": "fixture timeout"}
        self.stop.side_effect = stop
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.restart)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.restart().status_code, 409)
            finally:
                release.set()
            self.assertEqual(first.result().status_code, 200)
        self.stop.side_effect = None
        self.assertTrue(self.restart().json()["ok"])

    def test_exit_marker_quoted_in_agent_output_is_not_proof_of_exit(self):
        self.assertFalse(dashboard._agent_exited("fixture", "The marker --- Agent exited --- is displayed after exit."))
        self.assertTrue(dashboard._agent_exited("fixture", "done\n--- Agent exited ---\n"))

    def test_remote_restart_proxies_once_and_qualifies_returned_ids(self):
        node = SimpleNamespace(id="remote", label="Remote", authorization_headers={"Authorization": "Bearer remote-token"},
                               connect_timeout_seconds=3, request_timeout_seconds=10,
                               upstream_url=lambda path: "https://fixture.invalid" + path)
        response = httpx.Response(200, json={"ok": True, "run_id": "new", "restarted_from": "source"})
        with patch.object(dashboard.RemoteNodeRegistry, "get", return_value=node), \
                patch.object(dashboard.httpx.AsyncClient, "request", new=AsyncMock(return_value=response)) as request:
            qualified = dashboard.qualify_run_id("remote", "source")
            result = self.client.post(f"/api/sessions/{qualified}/restart", headers={"Authorization": "Bearer fixture-token"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["run_id"], dashboard.qualify_run_id("remote", "new"))
        self.assertEqual(result.json()["restarted_from"], qualified)
        request.assert_awaited_once()
        self.assertEqual(request.call_args.args[:2], ("POST", "https://fixture.invalid/api/sessions/source/restart"))
        self.assertEqual(request.call_args.kwargs["timeout"].read, 60)
        self.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
