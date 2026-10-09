from contextlib import ExitStack
import httpx
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, secret_input


class PrivateInputTests(unittest.TestCase):
    def test_retired_helper_never_pastes_to_a_terminal(self):
        with patch('subprocess.run') as run:
            self.assertFalse(secret_input.send('%7', b'fixture-not-a-real-key', True))
            run.assert_not_called()

    def test_legacy_api_cannot_deliver_to_any_terminal(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE': '0'}))
            lookup = stack.enter_context(patch.object(dashboard, '_lookup_run_light'))
            target = stack.enter_context(patch.object(dashboard, '_tmux_target_pane'))
            send = stack.enter_context(patch.object(secret_input, 'send'))
            app = dashboard.create_app(Path(temporary), token='fixture-auth', ttyd_enabled=False, remote_nodes_enabled=False)
            client = stack.enter_context(TestClient(app, base_url='https://testserver'))
            for agent in ('claude', 'codex', 'cursor', 'terminal', ''):
                lookup.return_value = {'agent':agent, 'tmux_session':'fixture'}
                response = client.post('/api/sessions/fixture/secret-input', content=b'fixture-not-a-real-key',
                                       headers={'Authorization':'Bearer fixture-auth'})
                self.assertEqual(response.status_code, 410)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertNotIn('fixture-not-a-real-key', response.text)
            lookup.assert_not_called(); target.assert_not_called(); send.assert_not_called()

    def test_legacy_remote_input_is_rejected_before_forwarding(self):
        from agent_orchestrator.remote_nodes import RemoteNodeRegistry, RemoteNodeSettings, qualify_run_id
        from urllib.parse import quote
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            registry = RemoteNodeRegistry([RemoteNodeSettings(id='fixture-node',label='Fixture',url='https://node.invalid',token='fixture-node-auth')])
            stack.enter_context(patch.object(dashboard, 'RemoteNodeRegistry', return_value=registry))
            stack.enter_context(patch.object(registry, 'start'))
            stack.enter_context(patch.object(registry, 'stop'))
            upstream = stack.enter_context(patch.object(httpx.AsyncClient, 'request', new_callable=AsyncMock))
            app = dashboard.create_app(Path(temporary), token='fixture-auth', ttyd_enabled=False)
            client = stack.enter_context(TestClient(app, base_url='https://testserver'))
            run_id = quote(qualify_run_id('fixture-node', 'fixture'), safe='')
            response = client.post('/api/sessions/'+run_id+'/secret-input', content=b'fixture', headers={'Authorization':'Bearer fixture-auth'})
            self.assertEqual(response.status_code, 410)
            upstream.assert_not_awaited()
