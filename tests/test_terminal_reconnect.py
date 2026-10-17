"""Transient inventory failures must not destroy healthy display connections."""
import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from agent_orchestrator import dashboard


class TerminalReconnectTests(unittest.TestCase):
    def test_inventory_failure_preserves_ttyd_and_shadow(self):
        for failure in (subprocess.TimeoutExpired('tmux', 5), OSError('temporarily unavailable')):
            with self.subTest(failure=type(failure).__name__):
                manager = dashboard.TtydManager(enabled=False)
                process = Mock()
                process.poll.return_value = None
                manager._procs = {'fixture': (process, 7800, '')}
                with patch.object(dashboard.subprocess, 'run', side_effect=failure), patch.object(dashboard, 'kill_shadow_session') as kill:
                    self.assertEqual(manager.reap_dead(min_interval_s=0), 0)
                process.terminate.assert_not_called()
                kill.assert_not_called()
                self.assertIn('fixture', manager._procs)

    def test_failed_inventory_is_not_an_empty_discovery(self):
        with tempfile.TemporaryDirectory() as root, patch.object(dashboard.subprocess, 'run', side_effect=subprocess.TimeoutExpired('tmux', 5)):
            with self.assertRaises(RuntimeError):
                dashboard._discover_runs(Path(root))

    def test_explicit_absent_server_remains_an_empty_inventory(self):
        with patch.object(dashboard.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='no server running on /tmp/tmux-test/default')):
            self.assertEqual(dashboard.tmux_list_sessions(strict=True), [])

    def test_unexpected_inventory_failure_is_unknown(self):
        with patch.object(dashboard.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='permission denied')):
            with self.assertRaises(RuntimeError):
                dashboard.tmux_list_sessions(strict=True)

    def test_browser_disconnect_releases_idle_upstream(self):
        import threading
        from fastapi.testclient import TestClient
        released = threading.Event()
        class Upstream:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                released.set()
            async def send(self, message):
                pass
            async def __aiter__(self):
                await asyncio.Event().wait()
                yield b''
        with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
            app = dashboard.create_app(Path('/nonexistent/siling-reconnect-test'), ttyd_enabled=True, remote_nodes_enabled=False)
        with patch.object(dashboard.TtydManager, 'port_for', return_value=12345), patch.object(dashboard.websockets, 'connect', return_value=Upstream()), TestClient(app) as client:
            with client.websocket_connect('/tty/fixture/ws'):
                pass
            self.assertTrue(released.wait(2), 'Idle relay must release its tmux client immediately after browser disconnect')

    def test_snapshot_retains_last_good_sessions_after_scan_failure(self):
        import time
        calls = 0
        def scan():
            nonlocal calls
            calls += 1
            if calls == 1:
                return [{"run_id": "fixture", "alive": True}]
            raise RuntimeError("tmux session inventory unavailable")
        service = dashboard.SessionSnapshotService(scan, interval_s=60)
        service.start()
        try:
            deadline = time.monotonic() + 2
            while not service.snapshot()["ready"] and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(service.snapshot()["ready"])
            service.request_refresh()
            deadline = time.monotonic() + 2
            while not service.snapshot()["error"] and time.monotonic() < deadline:
                time.sleep(.01)
            state = service.snapshot()
            self.assertTrue(state["error"])
            self.assertEqual(state["sessions"], [{"run_id": "fixture", "alive": True}])
        finally:
            service.stop()
