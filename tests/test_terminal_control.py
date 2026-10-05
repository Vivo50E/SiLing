import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from agent_orchestrator import terminal_control as control


class TerminalControlTests(unittest.TestCase):
    def setUp(self):
        self.uid = os.getuid()
        self.pane = '%7\t100\t/dev/ttys007\tssh\n'
        self.rows = self.row(100, 1, 100, 110, '/bin/bash') + self.row(110, 100, 110, 110, '/usr/bin/ssh')

    def row(self, pid, parent, group, foreground, command, uid=None, tty='ttys007'):
        return f'{pid} {parent} {group} {foreground} {self.uid if uid is None else uid} {tty} Mon Oct 5 12:00:00 2026 {command}\n'

    def inspect(self, rows=None, pane=None):
        with patch.object(control, '_run', side_effect=[pane or self.pane, rows or self.rows]):
            return control.inspect_ssh('%7')

    def test_identifies_foreground_descendant_only_and_signals_single_pid(self):
        background = self.row(120, 100, 120, 110, '/usr/bin/ssh')
        other = self.row(130, 1, 110, 110, '/usr/bin/ssh')
        inspected = self.inspect(self.rows + background + other)
        with patch.object(control, '_run', side_effect=[self.pane, self.rows]), patch.object(control.os, 'kill') as kill:
            result = control.disconnect_ssh('%7', inspected['token'])
        kill.assert_called_once_with(110, signal.SIGTERM)
        self.assertEqual(result['status'], 'disconnect_requested')

    def test_changed_process_identity_rejects_stale_confirmation(self):
        inspected = self.inspect()
        changed = self.rows.replace('12:00:00', '12:00:01')
        with patch.object(control, '_run', side_effect=[self.pane, changed]), patch.object(control.os, 'kill') as kill:
            with self.assertRaisesRegex(ValueError, 'changed'):
                control.disconnect_ssh('%7', inspected['token'])
        kill.assert_not_called()

    def test_never_signals_shell_other_user_other_tty_or_ambiguous_ssh(self):
        variants = [self.row(100, 1, 100, 100, '/usr/bin/ssh'),
                    self.row(100, 1, 100, 110, '/bin/bash') + self.row(110, 100, 110, 110, '/usr/bin/ssh', uid=self.uid+1),
                    self.row(100, 1, 100, 110, '/bin/bash') + self.row(110, 100, 110, 110, '/usr/bin/ssh', tty='ttys008'),
                    self.rows + self.row(111, 100, 110, 110, '/usr/bin/ssh')]
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.inspect(rows)
        with self.assertRaises(ValueError):
            self.inspect(pane='%7\t100\t/dev/ttys007\tbash\n')

    def test_api_binds_inspection_to_terminal_session(self):
        from agent_orchestrator import dashboard
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'fixture'
            folder.mkdir()
            meta = folder / 'session.json'
            meta.write_text(json.dumps({'name': 'shell', 'agent': 'terminal', 'tmux_session': 'fixture-tmux'}))
            with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
                app = dashboard.create_app(root, token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
            client = TestClient(app)
            self.addCleanup(client.close)
            headers = {'Authorization': 'Bearer fixture'}
            route = '/api/sessions/fixture::shell/ssh-control'
            self.assertEqual(client.get(route).status_code, 401)
            with patch.object(dashboard, '_tmux_target_pane', return_value=('%7', '')), patch.object(
                control, 'inspect_ssh', return_value={'token': 'checked', 'pid': 110}
            ), patch.object(control, 'disconnect_ssh', return_value={'ok': True}) as disconnect:
                self.assertEqual(client.get(route, headers=headers).json(), {'token': 'checked'})
                self.assertEqual(client.post(route, headers=headers, json={'token': 'checked'}).status_code, 200)
                disconnect.assert_called_once_with('%7', 'checked')
                meta.write_text(json.dumps({'name': 'shell', 'agent': 'claude', 'tmux_session': 'fixture-tmux'}))
                self.assertEqual(client.post(route, headers=headers, json={'token': 'checked'}).status_code, 409)

    def test_real_stalled_ssh_exits_without_closing_shell(self):
        # Local TCP fixture accepts SSH then never finishes its handshake.
        # No remote login, real account, agent, or user tmux session is touched.
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(5)
        name = 'siling-ssh-test-' + uuid.uuid4().hex[:12]
        def tmux(*args):
            return subprocess.run(['tmux', *args], text=True, capture_output=True, timeout=5, check=True).stdout.strip()
        tmux('new-session', '-d', '-s', name, '/bin/bash --noprofile --norc')
        self.addCleanup(lambda: subprocess.run(['tmux', 'kill-session', '-t', name], capture_output=True, timeout=5))
        pane = tmux('display-message', '-p', '-t', name, '#{pane_id}')
        command = f'ssh -F /dev/null -o BatchMode=yes -p {listener.getsockname()[1]} 127.0.0.1'
        tmux('send-keys', '-t', pane, '-l', command)
        tmux('send-keys', '-t', pane, 'Enter')
        conn, _ = listener.accept()
        self.addCleanup(conn.close)
        inspected = control.inspect_ssh(pane)
        started = time.monotonic()
        control.disconnect_ssh(pane, inspected['token'])
        while time.monotonic() - started < 3:
            if tmux('display-message', '-p', '-t', pane, '#{pane_current_command}') == 'bash':
                break
            time.sleep(.05)
        self.assertEqual(tmux('display-message', '-p', '-t', pane, '#{pane_current_command}'), 'bash')
        self.assertLess(time.monotonic() - started, 3)
        tmux('send-keys', '-t', pane, '-l', 'echo SILINGSHELLALIVE')
        tmux('send-keys', '-t', pane, 'Enter')
        time.sleep(.1)
        self.assertIn('SILINGSHELLALIVE', tmux('capture-pane', '-p', '-t', pane))
