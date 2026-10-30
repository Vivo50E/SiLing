import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import shutil
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, jira_mcp
from agent_orchestrator.pane_groups import PaneGroups

FIXTURE = Path(__file__).parent / 'fixtures' / 'jira_mcp_server.py'


class JiraMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.outputs = self.root / 'outputs'
        self.manager = jira_mcp.JiraMCP(self.outputs)
        self.record = self.root / 'requests.jsonl'
        self.config = self.root / 'mcp.json'
        self.server = {'command': sys.executable, 'args': [str(FIXTURE)],
                       'env': {'FIXTURE_RECORD': str(self.record), 'JIRA_URL': 'https://jira.example'}}
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        self.body = {'config_file': str(self.config), 'server_name': 'jira', 'base_url': ''}
        self.index = self.root / 'index'

    def connect(self):
        with patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': []}):
            self.assertTrue(self.manager.connect(self.body)['enabled'])

    def rows(self, keys):
        return {'items': [{'key': key, 'title': f'Title {key}', 'state': 'Open'} for key in keys], 'failed': []}

    def test_real_stdio_handshake_only_fixed_tool_and_minimal_fields(self):
        shutil.copyfile(FIXTURE, self.root / 'server.py')
        self.server['args'] = ['server.py']
        self.server['env']['FIXTURE_PAGED'] = '1'
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        status = self.manager.connect(self.body)
        self.assertTrue(status['enabled'])
        self.assertNotIn('env', json.dumps(status))
        response = self.manager.discover({}, 'DEMO-12 WRONG-1 FAIL-1 WRAPPED-1 secret terminal content', self.index)
        self.assertEqual([(i['key'], i['state']) for i in response['items']], [('DEMO-12', 'In Progress'), ('WRAPPED-1', 'In Progress')])
        self.assertEqual(response['failed'], 2)
        self.assertNotIn('private-provider-error', json.dumps(response))
        requests = [json.loads(line) for line in self.record.read_text().splitlines()]
        calls = [r for r in requests if r['method'] == 'tools/call']
        self.assertEqual(len(calls), 4)
        self.assertTrue(any(r['method'] == 'tools/list' and r.get('params', {}).get('cursor') == 'fixture-page-2' for r in requests))
        self.assertTrue(all(r['params']['name'] == 'jira_get_issue' for r in calls))
        self.assertEqual(calls[0]['params']['arguments'], {'issue_key': 'DEMO-12', 'fields': 'summary,status'})
        self.assertNotIn('secret terminal content', self.record.read_text())
        self.assertEqual(self.manager.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.index / 'jira.json').stat().st_mode & 0o777, 0o600)

    def test_unsupported_tool_cannot_be_selected_from_server_description(self):
        result = jira_mcp.call_worker({**self.server, 'env': {'FIXTURE_TOOL': 'jira_create_issue'}}, ['DEMO-12'])
        self.assertEqual(result, {'error': 'unsupported_tool'})

    def test_real_streamable_http_auth_and_cross_origin_redirect_rejection(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path, self.headers.get('Authorization'), request))
                if self.path == '/redirect':
                    self.send_response(307)
                    self.send_header('Location', f'http://localhost:{self.server.server_port}/never-send-credentials')
                    self.end_headers()
                    return
                if 'id' not in request:
                    self.send_response(202)
                    self.end_headers()
                    return
                if request['method'] == 'initialize':
                    result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}},
                              'serverInfo': {'name': 'fixture', 'version': '1'}}
                elif request['method'] == 'tools/list':
                    result = {'tools': [{'name': 'jira_get_issue', 'inputSchema': {'type': 'object',
                              'properties': {'issue_key': {'type': 'string'}}, 'required': ['issue_key']}}]}
                else:
                    result = {'content': [], 'structuredContent': {'key': request['params']['arguments']['issue_key'],
                                                                  'summary': 'HTTP fixture', 'status': 'Done'}}
                raw = json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_DELETE(self):
                self.send_response(204)
                self.end_headers()
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever)
        thread.start()
        try:
            base = f'http://127.0.0.1:{http.server_port}'
            server = {'url': base + '/mcp', 'headers': {'Authorization': 'Bearer fixture-credential'}}
            response = jira_mcp.call_worker(server, ['DEMO-4'])
            self.assertEqual(response['items'], [{'key': 'DEMO-4', 'title': 'HTTP fixture', 'state': 'Done'}])
            self.assertTrue(all(row[1] == 'Bearer fixture-credential' for row in seen))
            redirect = jira_mcp.call_worker({**server, 'url': base + '/redirect'}, ['DEMO-4'])
            self.assertEqual(redirect, {'error': 'connection_failed'})
            self.assertNotIn('fixture-credential', json.dumps(redirect))
            self.assertEqual(len([row for row in seen if row[0] == '/redirect']), 1)
            self.assertFalse(any(row[0] == '/never-send-credentials' for row in seen))
        finally:
            http.shutdown()
            http.server_close()
            thread.join(5)

    def test_agent_branch_and_saved_review_titles_are_evidence_but_shell_cwd_is_not(self):
        self.connect()
        repo = self.root / 'repo'
        subprocess.run(['git', 'init', '--quiet', '--initial-branch=fix/DEMO-7', str(repo)], check=True)
        self.index.mkdir()
        (self.index / 'reviews.json').write_text(json.dumps({'items': [{'title': 'Fix REVIEW-8'}]}))
        with patch.object(jira_mcp, 'call_worker', side_effect=lambda server, keys: self.rows(keys)) as worker:
            data = self.manager.discover({'agent': 'codex', 'cwd': str(repo)}, '', self.index)
            self.assertEqual({i['key'] for i in data['items']}, {'DEMO-7', 'REVIEW-8'})
            self.manager.discover({'agent': 'terminal', 'cwd': str(repo)}, '', self.root / 'shell-index')
            self.assertEqual(worker.call_count, 1)

    def test_config_listing_expansion_and_no_secret_copy(self):
        self.server['env']['JIRA_API_TOKEN'] = '${FIXTURE_JIRA_TOKEN}'
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        self.assertEqual(jira_mcp.server_config(self.config, None), [{'name': 'jira'}])
        with patch.dict(os.environ, {'FIXTURE_JIRA_TOKEN': 'fixture-credential'}):
            self.connect()
            self.assertNotIn('fixture-credential', self.manager.path.read_text())
            self.assertNotIn('JIRA_API_TOKEN', self.manager.path.read_text())
        for url in ['https://secret@jira.example', 'http://jira.example', 'https://jira.example/?token=secret',
                    'file:///tmp/mcp', 'https://jira.example/../other', 'https://jira.example:wrong-port']:
            with self.assertRaises(ValueError):
                jira_mcp.web_base(url)
        self.assertEqual(jira_mcp.web_base('http://127.0.0.1:9999/mcp'), 'http://127.0.0.1:9999/mcp')
        self.assertEqual(jira_mcp.web_base('HTTPS://JIRA.EXAMPLE/jira/'), 'https://jira.example/jira')

    def test_auto_associations_ttl_manual_label_force_and_restart(self):
        self.connect()
        run = {'display_name': 'Fix DEMO-1', 'linked_folders': [{'path': 'https://jira.example/browse/DEMO-1', 'label': 'Custom'}]}
        with patch.object(jira_mcp, 'call_worker', return_value=self.rows(['DEMO-1'])) as worker:
            first = self.manager.discover(run, 'DEMO-1', self.index)
            self.assertEqual(first['items'][0]['title'], 'Custom')
            self.manager.discover(run, 'DEMO-1', self.index)
            self.assertEqual(worker.call_count, 1)
            cached = jira_mcp.JiraMCP(self.outputs).discover({}, '', self.index)
            self.assertEqual(cached['items'][0]['title'], 'Title DEMO-1')
            self.manager.discover(run, '', self.index, force=True)
            self.assertEqual(worker.call_count, 2)
            self.manager.disconnect()
            self.assertEqual(len(self.manager.discover({}, '', self.index)['items']), 1)
            self.assertEqual(worker.call_count, 2)

    def test_only_evidence_keys_and_verified_matching_responses_link(self):
        self.connect()
        with patch.object(jira_mcp, 'call_worker', return_value=self.rows(['OTHER-999', 'DEMO-1'])) as worker:
            data = self.manager.discover({'initial_prompt': 'https://unrelated.example/browse/FOREIGN-5'}, '\x1b[31mDEMO-1\x1b[0m https://unrelated.example/browse/OTHER-2 lower-3 XDEMO-0', self.index)
        self.assertEqual(worker.call_args.args[1], ['DEMO-1'])
        self.assertEqual([i['key'] for i in data['items'] if i['source'] == 'mcp'], ['DEMO-1'])

    def test_budget_batches_make_progress_and_cache_only_never_calls_worker(self):
        self.connect()
        text = ' '.join(f'DEMO-{i}' for i in range(1, 14))
        with patch.object(jira_mcp, 'call_worker', side_effect=lambda server, keys: self.rows(keys)) as worker:
            first = self.manager.discover({}, text, self.index)
            self.assertEqual(first['pending'], 5)
            self.assertEqual(len(first['items']), 8)
            second = self.manager.discover({}, text, self.index)
            self.assertEqual(second['pending'], 0)
            self.assertEqual(len(second['items']), 13)
            self.manager.discover({}, 'NEW-999', self.index, lookup=False)
            self.assertEqual(worker.call_count, 2)

    def test_changed_config_requires_explicit_reconnect_and_failure_retains_history(self):
        self.connect()
        with patch.object(jira_mcp, 'call_worker', return_value=self.rows(['DEMO-1'])):
            self.manager.discover({}, 'DEMO-1', self.index)
        self.server['args'].append('--changed')
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        with patch.object(jira_mcp, 'call_worker') as worker:
            data = self.manager.discover({}, 'NEW-2', self.index)
            worker.assert_not_called()
        self.assertEqual(data['mcp_error'], 'config_changed')
        self.assertEqual(len(data['items']), 1)
        self.connect()
        with patch.object(jira_mcp, 'call_worker', return_value={'error': 'connection_failed'}):
            self.assertEqual(len(self.manager.discover({}, 'NEW-2', self.index)['items']), 1)

    def test_disconnect_during_query_does_not_save_results(self):
        self.connect()
        started, release = threading.Event(), threading.Event()
        def query(server, keys):
            started.set()
            self.assertTrue(release.wait(10))
            return self.rows(keys)
        replies = []
        with patch.object(jira_mcp, 'call_worker', side_effect=query):
            thread = threading.Thread(target=lambda: replies.append(self.manager.discover({}, 'DEMO-1', self.index)))
            thread.start()
            try:
                self.assertTrue(started.wait(10))
                self.manager.disconnect()
            finally:
                release.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(replies[0]['mcp_error'], 'config_changed')
        self.assertFalse((self.index / 'jira.json').exists())

    def test_reconnect_identity_invalidates_inflight_work_and_global_slots_are_bounded(self):
        self.connect()
        before = jira_mcp.read_json(self.manager.path)['connection_id']
        self.manager.disconnect()
        self.connect()
        self.assertNotEqual(jira_mcp.read_json(self.manager.path)['connection_id'], before)
        self.manager.slots.acquire()
        self.manager.slots.acquire()
        try:
            with patch.object(jira_mcp, 'call_worker') as worker:
                self.assertEqual(self.manager.connect(self.body)['error'], 'busy')
                self.assertEqual(self.manager.discover({}, 'DEMO-1', self.index)['mcp_error'], 'busy')
                worker.assert_not_called()
        finally:
            self.manager.slots.release()
            self.manager.slots.release()

    def test_disconnect_cancels_connect_attempt_and_malformed_worker_output_is_not_success(self):
        def connecting(server, keys):
            self.manager.disconnect()
            return {'items': [], 'failed': []}
        with patch.object(jira_mcp, 'call_worker', side_effect=connecting):
            self.assertEqual(self.manager.connect(self.body), {'error': 'config_changed'})
            self.assertFalse(self.manager.status()['enabled'])
        # Scope the mock to this module; do not intercept unrelated background workers.
        with patch.object(jira_mcp, 'subprocess', spec=subprocess) as process_module:
            process_module.TimeoutExpired = subprocess.TimeoutExpired
            process = process_module.Popen.return_value.__enter__.return_value
            process.returncode = 0
            for stdout in ('{}', '[]', 'not json'):
                process.communicate.return_value = (stdout, None)
                self.assertEqual(jira_mcp.call_worker(self.server, []), {'error': 'connection_failed'})
            process.communicate.side_effect = [subprocess.TimeoutExpired('fixture', 32), ('', None)]
            self.assertEqual(jira_mcp.call_worker(self.server, []), {'error': 'connection_failed'})
            process.terminate.assert_called_once()
            process.kill.assert_not_called()

    def test_route_auth_intent_configuration_errors_and_lookup_opt_in(self):
        self.outputs.mkdir()
        app = dashboard.create_app(self.outputs, token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
        headers = {'Authorization': 'Bearer fixture', 'X-Siling-Jira-MCP': 'user-click'}
        run = {'run_id': 'fixture', 'agent': 'terminal', 'display_name': 'DEMO-1'}
        original = dashboard._lookup_run_light
        lookup = lambda outputs, run_id: run if outputs == self.outputs and run_id == 'fixture' else original(outputs, run_id)
        with TestClient(app) as client, patch.object(dashboard, '_lookup_run_light', side_effect=lookup), \
                patch.object(jira_mcp, 'call_worker', side_effect=lambda server, keys: self.rows(keys)) as worker:
            self.assertEqual(client.get('/api/jira/mcp').status_code, 401)
            self.assertEqual(client.post('/api/jira/mcp/connect', json=self.body, headers={'Authorization': 'Bearer fixture'}).status_code, 403)
            self.assertEqual(client.post('/api/jira/mcp/connect', json=self.body, headers={**headers, 'Origin': 'https://evil.example'}).status_code, 403)
            self.assertTrue(client.post('/api/jira/mcp/connect', json=self.body, headers=headers).json()['enabled'])
            self.assertEqual(client.get('/api/sessions/fixture/jira', headers=headers).json()['items'], [])
            worker.assert_called_once()
            groups = PaneGroups(self.outputs)
            groups.change({'action': 'create', 'name': 'Jira', 'color': 'blue', 'jira_enabled': True})
            gid = groups.view([])['groups'][0]['id']
            groups.change({'action': 'assign', 'group_id': gid, 'run_id': 'fixture'}, [run])
            self.assertEqual(client.get('/api/sessions/fixture/jira?lookup=true', headers=headers).json()['items'][0]['key'], 'DEMO-1')
            self.assertEqual(worker.call_count, 2)
            response = client.post('/api/jira/mcp/servers', json={'config_file': str(self.config)}, headers=headers)
            self.assertEqual(response.json(), {'servers': [{'name': 'jira'}]})
            self.config.write_text('private-provider-secret')
            response = client.post('/api/jira/mcp/connect', json=self.body, headers=headers)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('private-provider-secret', response.text)
