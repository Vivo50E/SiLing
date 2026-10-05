import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class PaneSwitchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.outputs = self.root / 'outputs'
        self.source = self.outputs / 'source'
        self.source.mkdir(parents=True)
        self.project = self.root / 'project with spaces'
        self.project.mkdir()
        self.document = self.project / 'spec.md'
        self.document.write_text('Fixture document')
        self.metadata = {'name': 'source', 'label': 'Fixture', 'agent': 'terminal',
                         'cwd': str(self.project), 'tmux_session': 'original-shell',
                         'terminal_theme': 'soft-green',
                         'linked_folders': [{'path': str(self.document), 'type': 'file', 'label': 'Spec'}]}
        self.save_source()
        self.scripts = self.root / 'scripts'
        self.scripts.mkdir()
        self.counter = self.root / 'counter'
        launcher = self.scripts / 'run.sh'
        launcher.write_text(f'#!{sys.executable}\n' + f'counter = {str(self.counter)!r}\n' + '''import json, os, pathlib, sys
counter = pathlib.Path(counter)
counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else '1')
a = sys.argv[1:]
folder = pathlib.Path(os.environ['ORCH_OUTPUTS_DIR']) / a[a.index('--run-name')+1]
folder.mkdir(parents=True)
(folder / 'session.json').write_text(json.dumps({'name': a[-2], 'agent': a[-3], 'cwd': a[-1], 'tmux_session': 'new-fixture'}))
print('Session: new-fixture')
print('Output: ' + str(folder))
''')
        launcher.chmod(0o700)
        for name, value in [('SCRIPTS_DIR', self.scripts), ('_preallocate_native_resume_meta', None),
                            ('_schedule_native_resume_capture', None), ('tmux_kill', None), ('tmux_send', None)]:
            patcher = patch.object(dashboard, name, value) if value is not None else patch.object(dashboard, name)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if name == '_preallocate_native_resume_meta':
                mocked.return_value = ({}, '')
            if name == 'tmux_kill':
                self.kill = mocked
            if name == 'tmux_send':
                self.send = mocked
        with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
            self.app = dashboard.create_app(self.outputs, token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer fixture'}
        self.route = '/api/sessions/source::source/switch-type'
        self.body = {'agent': 'codex', 'request_id': 'switch-1'}

    def save_source(self):
        (self.source / 'session.json').write_text(json.dumps(self.metadata))

    def post(self, body=None):
        return self.client.post(self.route, headers=self.headers, json=self.body if body is None else body)

    def test_switch_preserves_source_and_copies_project_theme_and_files(self):
        before = (self.source / 'session.json').read_text()
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result['source_preserved'])
        self.assertEqual(result['switched_from'], 'source::source')
        child = json.loads((Path(result['run_dir']) / 'session.json').read_text())
        self.assertEqual(child['cwd'], str(self.project))
        self.assertEqual(child['agent'], 'codex')
        self.assertEqual(child['linked_folders'][0]['path'], str(self.document))
        self.assertIn('soft-green', result['command'])
        self.assertEqual((self.source / 'session.json').read_text(), before)
        self.kill.assert_not_called()
        self.send.assert_not_called()

    def test_retry_is_idempotent_and_changed_request_does_not_spawn(self):
        first = self.post().json()
        second = self.post().json()
        self.assertEqual(first['run_id'], second['run_id'])
        self.assertTrue(second['replayed'])
        self.assertEqual(self.counter.read_text(), '1')
        self.assertEqual(self.post({**self.body, 'agent': 'claude'}).status_code, 409)
        self.assertEqual(self.counter.read_text(), '1')

    def test_agent_to_terminal_ignores_agent_model_and_effort(self):
        self.metadata['agent'] = 'cursor'
        self.save_source()
        response = self.post({'agent': 'terminal', 'model': 'old-model', 'effort': 'high', 'request_id': 'switch-2'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('--model', response.json()['command'])
        self.assertNotIn('--effort', response.json()['command'])
        self.assertEqual(json.loads((Path(response.json()['run_dir']) / 'session.json').read_text())['agent'], 'terminal')

    def test_invalid_requests_never_start_a_session(self):
        self.assertEqual(self.client.post(self.route, json=self.body).status_code, 401)
        for invalid in [[], {}, {'agent':'terminal','request_id':'same'}, {'agent':'shell','request_id':'x'},
                        {**self.body, 'cwd': []}, {**self.body, 'label': 'x'*161}]:
            self.assertEqual(self.post(invalid).status_code, 400)
        self.assertFalse(self.counter.exists())

    def test_remote_controls_proxy_to_source_node_and_qualify_new_session(self):
        import os
        import httpx
        from unittest.mock import AsyncMock
        from agent_orchestrator.remote_nodes import qualify_run_id
        config = self.root / 'dashboard.local.json'
        config.write_text(json.dumps({'remote_nodes': [{'id': 'dev', 'label': 'Fixture node',
                            'url': 'http://127.0.0.1:17861', 'token': 'fixture-remote-token'}]}))
        with patch.dict(os.environ, {'ORCH_DASHBOARD_CONFIG': str(config)}):
            app = dashboard.create_app(self.outputs, token='fixture', ttyd_enabled=False)
        client = TestClient(app)
        self.addCleanup(client.close)
        remote_id = qualify_run_id('dev', 'source::source')
        response = httpx.Response(200, json={'run_id': 'child::variant', 'switched_from': 'source::source'})
        with patch.object(httpx.AsyncClient, 'request', new=AsyncMock(return_value=response)) as proxy:
            result = client.post(f'/api/sessions/{remote_id}/switch-type', headers=self.headers, json=self.body)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['run_id'], qualify_run_id('dev', 'child::variant'))
            self.assertEqual(result.json()['switched_from'], remote_id)
            args = proxy.call_args.args
            self.assertTrue(args[1].endswith('/api/sessions/source%3A%3Asource/switch-type'), args)
            self.assertEqual(proxy.call_args.kwargs['headers']['Authorization'], 'Bearer fixture-remote-token')
        with patch.object(httpx.AsyncClient, 'request', new=AsyncMock(return_value=httpx.Response(200, json={'token':'remote-token'}))), patch.object(dashboard.terminal_control, 'inspect_ssh') as inspect:
            result = client.get(f'/api/sessions/{remote_id}/ssh-control', headers=self.headers)
            self.assertEqual(result.json(), {'token':'remote-token'})
            inspect.assert_not_called()
