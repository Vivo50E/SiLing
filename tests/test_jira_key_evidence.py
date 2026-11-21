import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_orchestrator import jira_mcp


class JiraKeyEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.manager = jira_mcp.JiraMCP(self.root / 'outputs')
        config = self.root / 'mcp.json'
        config.write_text(json.dumps({'mcpServers': {'jira': {'url': 'https://mcp.example/mcp'}}}))
        with patch.object(jira_mcp, 'call_worker', return_value={'items': []}):
            self.manager.connect({'config_file': str(config), 'server_name': 'jira',
                                  'base_url': 'https://jira.example', 'project_key': 'DEMO'})
        self.index = self.root / 'index'

    @staticmethod
    def rows(server, keys):
        return {'items': [{'key': key, 'title': 'Fixture', 'state': 'Open'} for key in keys]}

    def test_protocol_versions_are_not_bare_ticket_keys(self):
        # Even without a project scope, a version suffix cannot be truncated.
        cfg = jira_mcp.read_json(self.manager.path)
        cfg.pop('project_key')
        self.manager.path.write_text(json.dumps(cfg))
        with patch.object(jira_mcp, 'call_worker', side_effect=self.rows) as worker:
            data = self.manager.discover({}, 'SSH-2.0 TLS-1.3 HTTP-1.1 DEMO-12.34 DEMO-9', self.index)
        self.assertEqual(worker.call_args.args[1], ['DEMO-9'])
        self.assertEqual([i['key'] for i in data['items']], ['DEMO-9'])

    def test_project_scope_and_explicit_cross_project_urls_survive_restart(self):
        with patch.object(jira_mcp, 'call_worker', side_effect=self.rows) as worker:
            data = self.manager.discover({}, 'SSH-2 OTHER-1 DEMO-2 https://jira.example/browse/OTHER-3', self.index)
            self.assertEqual(worker.call_args.args[1], ['DEMO-2', 'OTHER-3'])
            self.assertEqual({i['key'] for i in data['items']}, {'DEMO-2', 'OTHER-3'})
            restarted = jira_mcp.JiraMCP(self.root / 'outputs')
            data = restarted.discover({}, '', self.index, force=True)
            self.assertEqual({i['key'] for i in data['items']}, {'DEMO-2', 'OTHER-3'})
            self.assertEqual(set(worker.call_args.args[1]), {'DEMO-2', 'OTHER-3'})

    def seed_cache(self):
        self.index.mkdir()
        rows = [{'url': 'https://jira.example/browse/' + key, 'key': key,
                 'title': 'Fixture', 'source': source, 'match': 'key'}
                for key, source in [('SSH-2', 'mcp'), ('DEMO-1', 'mcp'),
                                    ('OTHER-3', 'linked'), ('OTHER-4', 'output')]]
        path = self.index / 'jira.json'
        path.write_text(json.dumps({'items': rows, 'attempts': {'SSH-2': 123}}))
        return path

    def test_legacy_cache_pruned_without_provider_calls_and_manual_links_kept(self):
        path = self.seed_cache()
        with patch.object(jira_mcp, 'call_worker') as worker:
            data = self.manager.discover({}, '', self.index, lookup=False)
            worker.assert_not_called()
        expected = {'DEMO-1', 'OTHER-3', 'OTHER-4'}
        self.assertEqual({i['key'] for i in data['items']}, expected)
        self.assertEqual({i['key'] for i in json.loads(path.read_text())['items']}, expected)

    def test_pruning_persists_when_provider_fails(self):
        path = self.seed_cache()
        with patch.object(jira_mcp, 'call_worker', return_value={'error': 'timeout'}):
            data = self.manager.discover({}, 'DEMO-2', self.index)
        self.assertEqual(data['mcp_error'], 'timeout')
        self.assertNotIn('SSH-2', {i['key'] for i in data['items']})
        self.assertNotIn('SSH-2', {i['key'] for i in json.loads(path.read_text())['items']})

    def test_current_explicit_url_rescues_legacy_association(self):
        self.seed_cache()
        with patch.object(jira_mcp, 'call_worker', side_effect=self.rows):
            data = self.manager.discover({}, 'https://jira.example/browse/SSH-2', self.index)
        self.assertIn('SSH-2', {i['key'] for i in data['items']})
        with patch.object(jira_mcp, 'call_worker', side_effect=self.rows):
            data = self.manager.discover({}, '', self.index, force=True)
        self.assertIn('SSH-2', {i['key'] for i in data['items']})

    def test_prior_search_links_survive_scope_change_and_key_refresh(self):
        path = self.seed_cache()
        saved = json.loads(path.read_text())
        saved['items'][0]['match'] = 'task'
        path.write_text(json.dumps(saved))
        with patch.object(jira_mcp, 'call_worker', side_effect=self.rows):
            self.manager.discover({}, '', self.index, force=True)
            data = self.manager.discover({}, '', self.index, force=True)
        self.assertIn('SSH-2', {i['key'] for i in data['items']})
