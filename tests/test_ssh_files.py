"""SSH preview transport, shell quoting and authenticated session routing."""
from contextlib import ExitStack
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, ssh_files


class SshFilesTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))

    def test_rejects_options_commands_and_relative_paths(self):
        for host, path in [("-ProxyCommand=id", "/a"), ("host;id", "/a"),
                           ("ssh host", "/a"), ("host", "a"), ("host", "//a"),
                           ("host", "/a\nb"), (None, "/a"), ("host", None), ("host", "/tmp/..")]:
            with self.subTest(host=host, path=path), self.assertRaises(ValueError):
                ssh_files.validate_target(host, path)
        ssh_files.validate_target("user@dev-server", "/tmp/file with 'quotes'.png")

    def test_real_reader_quotes_paths_preserves_bytes_and_refreshes(self):
        source = self.root / "image '$(false); 文件.png"
        source.write_bytes(b"\x89PNG\x00\xff")
        run = subprocess.run
        def local_transport(argv, **kwargs):
            self.assertIn("BatchMode=yes", argv)
            self.assertIn("StrictHostKeyChecking=yes", argv)
            remote_argv = shlex.split(argv[-1])
            self.assertEqual(remote_argv[3], str(source))
            remote_argv[0] = sys.executable
            return run(remote_argv, **kwargs)
        with patch.object(ssh_files.subprocess, "run", side_effect=local_transport):
            target = ssh_files.fetch_preview("dev", str(source), self.root / "cache")
            self.assertEqual(target.read_bytes(), source.read_bytes())
            source.write_bytes(b"refreshed")
            self.assertEqual(ssh_files.fetch_preview("dev", str(source), self.root / "cache"), target)
            self.assertEqual(target.read_bytes(), b"refreshed")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with patch.object(ssh_files.subprocess, "run", return_value=subprocess.CompletedProcess([], 255, stderr=b"Permission denied")):
            with self.assertRaisesRegex(ValueError, "Permission denied"):
                ssh_files.fetch_preview("dev", str(source), self.root / "cache")
        self.assertEqual(target.read_bytes(), b"refreshed")


    def test_reader_rejects_missing_directory_fifo_and_oversize(self):
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        big = self.root / "big"
        big.write_bytes(b"0123456789")
        for path in [self.root / "missing", self.root, fifo, big]:
            result = subprocess.run([sys.executable, "-c", ssh_files.REMOTE_READER,
                                     str(path), "5"], capture_output=True, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")

    def test_failed_transfer_does_not_publish_partial_snapshot(self):
        for error in [subprocess.TimeoutExpired("ssh", 25), OSError("missing ssh")]:
            with patch.object(ssh_files.subprocess, "run", side_effect=error):
                with self.assertRaises(ValueError):
                    ssh_files.fetch_preview("dev", "/tmp/a", self.root / "cache")
        self.assertEqual(list((self.root / "cache").rglob("a")), [])

    def test_api_requires_auth_existing_run_and_links_snapshot(self):
        self.stack.enter_context(patch.dict(os.environ, {
            "ORCH_DASHBOARD_CONFIG": str(self.root / "missing.json"),
            "ORCH_ACTIVE_SNAPSHOT_AUTOSAVE": "0",
        }))
        app = dashboard.create_app(self.root, token="test-secret", ttyd_enabled=False,
                                   remote_nodes_enabled=False)
        client = TestClient(app)
        self.addCleanup(client.close)
        lookup = self.stack.enter_context(patch.object(dashboard, "_lookup_run_light", return_value=None))
        fetch = self.stack.enter_context(patch.object(dashboard, "fetch_ssh_preview"))
        headers = {"Authorization": "Bearer test-secret"}
        payload = {"host": "dev", "path": "/tmp/image.png"}
        self.assertEqual(client.post('/api/sessions/test/ssh-file', json=payload).status_code, 401)
        self.assertEqual(client.post('/api/sessions/test/ssh-file', headers=headers, json=payload).status_code, 404)
        fetch.assert_not_called()
        lookup.return_value = {"run_dir": str(self.root), "kind": "run"}
        (self.root / "session.json").write_text('{}')
        cached = self.root / "snapshot.png"
        cached.write_bytes(b"sample")
        fetch.return_value = cached
        with patch.object(dashboard, "_is_allowed_linked_folder", return_value=False):
            response = client.post('/api/sessions/test/ssh-file', headers=headers, json=payload)
        self.assertEqual(response.status_code, 400)
        fetch.assert_not_called()
        with patch.object(dashboard, "_is_allowed_linked_folder", return_value=True):
            response = client.post('/api/sessions/test/ssh-file', headers=headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['folder']['path'], str(cached.resolve()))
        self.assertIn('dev:/tmp/image.png', (self.root / "session.json").read_text())
