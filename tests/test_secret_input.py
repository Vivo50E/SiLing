from contextlib import ExitStack
import hashlib
import json
import httpx
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, secret_input


class PrivateInputTests(unittest.TestCase):
    def test_value_only_uses_stdin_and_private_buffer_is_deleted(self):
        value = b'fixture-private-$() token'
        success = subprocess.CompletedProcess([], 0)
        with patch.object(secret_input.subprocess, 'run', return_value=success) as run:
            self.assertTrue(secret_input.send('%7', value, True))
        load, paste, delete = run.call_args_list
        self.assertEqual(load.kwargs['input'], value + b'\r')
        self.assertEqual(load.args[0][:3], ['tmux', 'load-buffer', '-b'])
        name = load.args[0][3]
        self.assertEqual(paste.args[0], ['tmux', 'paste-buffer', '-d', '-r', '-b', name, '-t', '%7'])
        self.assertEqual(delete.args[0], ['tmux', 'delete-buffer', '-b', name])
        for call in run.call_args_list:
            self.assertNotIn(value.decode(), repr(call.args))
            self.assertEqual(call.kwargs['stderr'], subprocess.DEVNULL)
            self.assertEqual(call.kwargs['stdout'], subprocess.DEVNULL)

    def test_uncertain_paste_is_not_retried_and_buffer_is_deleted(self):
        with patch.object(secret_input.subprocess, 'run', side_effect=[
                subprocess.CompletedProcess([], 0), subprocess.TimeoutExpired(['tmux'], 5),
                subprocess.CompletedProcess([], 0)]) as run:
            self.assertFalse(secret_input.send('%7', b'fixture', False))
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[-1].args[0][1], 'delete-buffer')

    def test_validation_never_invokes_tmux_or_reflects_input(self):
        for value in (b'', b'x' * 4097, b'fixture\nvalue', b'fixture\x1bvalue', b'fixture\x7fvalue', b'\xff'):
            with patch.object(secret_input.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    secret_input.send('%7', value, False)
                run.assert_not_called()
        self.assertTrue(secret_input.trusted_transport('https', '192.0.2.1'))
        self.assertTrue(secret_input.trusted_transport('http', '::1'))
        self.assertFalse(secret_input.trusted_transport('http', '192.0.2.1'))
        self.assertFalse(secret_input.trusted_transport('http', 'unknown'))

    def test_api_auth_transport_validation_and_generic_errors(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE': '0'}))
            stack.enter_context(patch.object(dashboard, '_lookup_run_light', return_value={'tmux_session':'fixture'}))
            target = stack.enter_context(patch.object(dashboard, '_tmux_target_pane', return_value=('%7', '')))
            send = stack.enter_context(patch.object(secret_input, 'send', return_value=True))
            app = dashboard.create_app(root, token='fixture-auth', ttyd_enabled=False, remote_nodes_enabled=False)
            client = stack.enter_context(TestClient(app, base_url='https://testserver'))
            url = '/api/sessions/fixture/secret-input'
            headers = {'Authorization':'Bearer fixture-auth', 'X-Siling-Secret-Enter':'true'}
            self.assertEqual(client.post(url, content=b'fixture').status_code, 401)
            self.assertEqual(client.post(url, content=b'fixture', headers=headers).json(), {'ok':True})
            send.assert_called_once_with('%7', b'fixture', True)
            send.reset_mock(); target.reset_mock()
            for content, code in [(b'fixture\nvalue', 400), (b'x' * 4097, 413), (b'\xff', 400)]:
                response = client.post(url, content=content, headers=headers)
                self.assertEqual(response.status_code, code)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertNotIn('fixture\nvalue', response.text)
            send.assert_not_called(); target.assert_not_called()
            send.return_value = False
            response = client.post(url, content=b'fixture-secret', headers=headers)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('fixture-secret', response.text)
            insecure = stack.enter_context(TestClient(app, base_url='http://testserver'))
            response = insecure.post(url, content=b'fixture-secret', headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_remote_private_delivery_requires_protected_transport_and_keeps_node_auth(self):
        from agent_orchestrator.remote_nodes import RemoteNodeRegistry, qualify_run_id
        from urllib.parse import quote
        for destination, allowed in [('http://192.0.2.1:7860', False),
                                     ('http://127.0.0.1:7860', True), ('https://node.example', True)]:
            with self.subTest(destination=destination), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                root = Path(temporary)
                config = root / 'config.json'
                config.write_text(json.dumps({'remote_nodes':[{'id':'dev','label':'Fixture node',
                                                              'url':destination,'token':'fixture-node-auth'}]}))
                stack.enter_context(patch.dict(os.environ, {'ORCH_DASHBOARD_CONFIG':str(config),
                                                            'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0'}))
                stack.enter_context(patch.object(RemoteNodeRegistry, 'start'))
                stack.enter_context(patch.object(RemoteNodeRegistry, 'stop'))
                upstream = stack.enter_context(patch.object(httpx.AsyncClient, 'request', new_callable=AsyncMock,
                                                            return_value=httpx.Response(200, json={'ok':True})))
                app = dashboard.create_app(root, token='fixture-dashboard-auth', ttyd_enabled=False)
                client = stack.enter_context(TestClient(app, base_url='https://testserver'))
                run_id = quote(qualify_run_id('dev', 'fixture-run'), safe='')
                response = client.post('/api/sessions/'+run_id+'/secret-input', content=b'fixture-private-value',
                                       headers={'Authorization':'Bearer fixture-dashboard-auth',
                                                'X-Siling-Secret-Enter':'false'})
                self.assertEqual(response.status_code, 200 if allowed else 403, response.text)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                if allowed:
                    upstream.assert_awaited_once()
                    kwargs = upstream.call_args.kwargs
                    self.assertEqual(kwargs['content'], b'fixture-private-value')
                    self.assertEqual(kwargs['headers']['Authorization'], 'Bearer fixture-node-auth')
                    self.assertNotIn('fixture-dashboard-auth', repr(kwargs['headers']))
                    self.assertTrue(upstream.call_args.args[1].endswith('/api/sessions/fixture-run/secret-input'))
                else:
                    upstream.assert_not_awaited()

    @unittest.skipUnless(shutil.which('tmux'), 'tmux required')
    def test_real_hidden_prompt_receives_exact_input_without_history_or_buffer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            socket = str(root / 'tmux.sock')
            script = root / 'prompt.py'
            script.write_text('''import hashlib
import json
import httpx, sys, termios
fd = sys.stdin.fileno()
previous = termios.tcgetattr(fd)
hidden = termios.tcgetattr(fd)
hidden[3] &= ~termios.ECHO
try:
    termios.tcsetattr(fd, termios.TCSANOW, hidden)
    print("PRIVATE_INPUT_READY", flush=True)
    value = sys.stdin.readline().removesuffix("\\n")
    print("RECEIVED_HASH=" + hashlib.sha256(value.encode()).hexdigest(), flush=True)
finally:
    termios.tcsetattr(fd, termios.TCSANOW, previous)
''')
            def tmux(*args):
                return subprocess.check_output(['tmux', '-S', socket, *args], text=True, timeout=5)
            command = shlex.join([sys.executable, str(script)]) + '; sleep 30'
            tmux('-f', '/dev/null', 'new-session', '-d', '-s', 'private-test', command)
            try:
                def capture():
                    return tmux('capture-pane', '-p', '-t', 'private-test', '-S', '-')
                for _ in range(100):
                    if 'PRIVATE_INPUT_READY' in capture():
                        break
                    time.sleep(.02)
                self.assertIn('PRIVATE_INPUT_READY', capture())
                pane = tmux('display-message', '-p', '-t', 'private-test', '#{pane_id}').strip()
                value = 'fixture-密钥-$() token '
                digest = hashlib.sha256(value.encode()).hexdigest()
                with patch.dict(os.environ, {'TMUX':socket + ',0,0'}):
                    self.assertTrue(secret_input.send(pane, value.encode(), True))
                for _ in range(100):
                    if digest in capture():
                        break
                    time.sleep(.02)
                output = capture()
                self.assertIn(digest, output)
                self.assertNotIn(value, output)
                self.assertNotIn('siling-private-', tmux('list-buffers'))
            finally:
                tmux('kill-server')
