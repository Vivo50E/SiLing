"""Read native MCP configuration without exporting credentials or running tools."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, jira_mcp


class NativeMCPTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.codex = self.root / 'config.toml'
        self.claude = self.root / '.claude.json'
        self.paths = [('codex', self.codex), ('claude', self.claude)]

    def test_discovery_lists_sources_without_resolving_or_exposing_credentials(self):
        self.codex.write_text('[mcp_servers.jira]\nurl="https://mcp.example/mcp"\n'
                              'bearer_token_env_var="UNSET_SECRET"\n'
                              '[mcp_servers.disabled]\ncommand="do-not-run"\nenabled=false\n')
        self.claude.write_text(json.dumps({'mcpServers': {
            'jira': {'url': 'https://other.example/mcp', 'headers': {'Authorization': 'private-fixture'}},
            'off': {'command': 'do-not-run', 'disabled': True}}}))
        with patch.object(jira_mcp, 'native_config_paths', return_value=self.paths), \
                patch.object(jira_mcp, 'call_worker') as worker:
            result = jira_mcp.native_servers()
        self.assertEqual([(i['source'], i['name']) for i in result['servers']], [('claude', 'jira'), ('codex', 'jira')])
        self.assertTrue(all(set(i) == {'source', 'config_file', 'name'} for i in result['servers']))
        self.assertNotIn('private-fixture', json.dumps(result))
        self.assertNotIn('mcp.example', json.dumps(result))
        worker.assert_not_called()
        self.claude.write_text('private-parser-error')
        self.codex.unlink()
        with patch.object(jira_mcp, 'native_config_paths', return_value=self.paths):
            result = jira_mcp.native_servers()
        self.assertEqual(result['servers'], [])
        self.assertEqual([i['status'] for i in result['sources']], ['missing', 'invalid'])
        self.assertNotIn('private-parser-error', json.dumps(result))

    def test_codex_headers_forwarded_environment_and_missing_variables(self):
        self.codex.write_text('[mcp_servers.jira]\nurl="https://mcp.example/mcp"\n'
                              'bearer_token_env_var="TOKEN"\n'
                              '[mcp_servers.jira.http_headers]\nAuthorization="stale"\nX-Static="value"\n'
                              '[mcp_servers.jira.env_http_headers]\nX-Region="REGION"\n')
        with patch.object(jira_mcp, 'os', SimpleNamespace(environ={'TOKEN': 'private-token', 'REGION': 'test'})):
            server = jira_mcp.server_config(str(self.codex), 'jira')
        self.assertEqual(server['headers'], {'Authorization': 'Bearer private-token', 'X-Static': 'value', 'X-Region': 'test'})
        with patch.object(jira_mcp, 'os', SimpleNamespace(environ={})), self.assertRaises(ValueError):
            jira_mcp.server_config(str(self.codex), 'jira')
        self.codex.write_text('[mcp_servers.jira]\ncommand="fixture"\nenv_vars=["FORWARD", {name="ALSO",source="local"}]\n'
                              '[mcp_servers.jira.env]\nFORWARD="override"\n')
        with patch.object(jira_mcp, 'os', SimpleNamespace(environ={'FORWARD': 'original', 'ALSO': 'inherited', 'UNRELATED': 'hidden'})):
            server = jira_mcp.server_config(str(self.codex), 'jira')
        self.assertEqual(server['env'], {'FORWARD': 'override', 'ALSO': 'inherited'})
        self.assertEqual(server['cwd'], str(self.root))

    def test_disabled_tools_helpers_and_remote_environment_do_not_silently_fall_back(self):
        for extra in ['enabled=false', 'enabled_tools=["jira_create_issue"]',
                      'disabled_tools=["jira_get_issue"]', 'env_vars=[{name="TOKEN",source="remote"}]']:
            self.codex.write_text('[mcp_servers.jira]\ncommand="do-not-run"\n' + extra + '\n')
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                jira_mcp.server_config(str(self.codex), 'jira')
        for extra in ['http_headers_helper="do-not-run"', 'auth="chatgpt"']:
            self.codex.write_text('[mcp_servers.jira]\nurl="https://mcp.example/mcp"\n' + extra + '\n')
            with patch.object(jira_mcp, 'call_worker') as worker:
                result = jira_mcp.JiraMCP(self.root / 'outputs').connect({
                    'config_file': str(self.codex), 'server_name': 'jira', 'base_url': 'https://jira.example'})
            self.assertEqual(result, {'error': 'native_auth_required'})
            worker.assert_not_called()

    def test_claude_environment_defaults_and_existing_json_format(self):
        self.claude.write_text(json.dumps({'mcpServers': {'jira': {
            'url': '${ENDPOINT:-https://mcp.example/mcp}',
            'headers': {'Authorization': 'Bearer ${TOKEN}', 'X-Optional': '${MISSING:-}'}}}}))
        with patch.object(jira_mcp, 'os', SimpleNamespace(environ={'TOKEN': 'fixture'})):
            server = jira_mcp.server_config(str(self.claude), 'jira')
        self.assertEqual(server['url'], 'https://mcp.example/mcp')
        self.assertEqual(server['headers'], {'Authorization': 'Bearer fixture', 'X-Optional': ''})

    def test_codex_home_is_respected_without_mutating_the_environment(self):
        with patch.object(jira_mcp, 'os', SimpleNamespace(environ={'CODEX_HOME': str(self.root)})):
            self.assertEqual(jira_mcp.native_config_paths()[0], ('codex', self.codex))

    def test_native_stdio_connect_and_lookup_keep_only_configuration_references(self):
        fixture = Path(__file__).parent / 'fixtures' / 'jira_mcp_server.py'
        self.codex.write_text('[mcp_servers.jira]\ncommand=' + json.dumps(sys.executable) + '\nargs=[' +
                              json.dumps(str(fixture)) + ']\n[mcp_servers.jira.env]\nJIRA_URL="https://jira.example"\n')
        manager = jira_mcp.JiraMCP(self.root / 'outputs')
        with patch.object(jira_mcp, 'native_config_paths', return_value=self.paths):
            connected = manager.connect({'config_file': str(self.codex), 'server_name': 'jira', 'base_url': ''})
        self.assertTrue(connected['enabled'])
        self.assertEqual(connected['config_source'], 'codex')
        self.assertNotIn('command', manager.path.read_text())
        result = manager.discover({}, 'DEMO-12', self.root / 'index')
        self.assertEqual(result['items'][0]['state'], 'In Progress')

    def test_local_discovery_route_requires_explicit_intent_and_never_returns_secrets(self):
        app = dashboard.create_app(self.root / 'outputs', token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
        payload = {'servers': [{'name': 'jira', 'source': 'codex', 'config_file': str(self.codex)}], 'sources': []}
        with TestClient(app) as client, patch.object(dashboard, 'jira_native_mcp_servers', return_value=payload):
            headers = {'Authorization': 'Bearer fixture', 'X-Siling-Jira-MCP': 'user-click'}
            self.assertEqual(client.post('/api/jira/mcp/local-servers', json={}).status_code, 401)
            self.assertEqual(client.post('/api/jira/mcp/local-servers', json={}, headers={'Authorization': 'Bearer fixture'}).status_code, 403)
            self.assertEqual(client.post('/api/jira/mcp/local-servers', json={}, headers={**headers, 'Origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/api/jira/mcp/local-servers', json={}, headers=headers).json(), payload)
            self.assertEqual(client.post('/api/jira/mcp/local-servers', json={'command': 'never'}, headers=headers).status_code, 400)
