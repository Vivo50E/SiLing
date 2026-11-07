import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_orchestrator import jira, jira_mcp


class JiraTaskSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / 'mcp.json'
        self.record = self.root / 'requests.jsonl'
        self.server = {'command': sys.executable,
                       'args': [str(Path(__file__).parent / 'fixtures/jira_mcp_server.py')],
                       'env': {'JIRA_URL': 'https://jira.example', 'FIXTURE_SEARCH': '1',
                               'FIXTURE_RECORD': str(self.record)}}
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        self.body = {'config_file': str(self.config), 'server_name': 'jira', 'base_url': ''}
        self.manager = jira_mcp.JiraMCP(self.root / 'outputs')
        self.index = self.root / 'index'

    def connect(self):
        with patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': [], 'search_supported': True}):
            self.manager.connect(self.body)

    def test_task_words_are_bounded_and_never_come_from_transcript_or_credentials(self):
        self.assertEqual(jira.task_terms({'display_name': 'SRAM Vmin Vmax (resume)'}), ['sram', 'vmin', 'vmax'])
        self.assertEqual(jira.task_terms({'display_name': 'interactive', 'initial_prompt': 'private SRAM Vmin prompt'}), [])
        for name in ['codex', 'fix', 'Bearer private-value', 'api_key=private-value', 'https://private.example/foo']:
            self.assertEqual(jira.task_terms({'display_name': name}), [])
        self.assertEqual(jira.task_terms({'display_name': '终端黑屏修复'}), ['终端黑屏修复'])
        self.assertFalse(jira.matches_task('SRAM Vminimum', ['sram', 'vmin']))

    def test_missing_and_invalid_site_are_distinct_from_mcp_authentication(self):
        self.server['env'].pop('JIRA_URL')
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        with patch.object(jira_mcp, 'call_worker', return_value={'error': 'auth_required'}) as worker:
            self.assertEqual(self.manager.connect(self.body), {'error': 'jira_url_required'})
            self.assertEqual(self.manager.connect({**self.body, 'base_url': 'https://token@jira.example'}), {'error': 'invalid_jira_url'})
            worker.assert_not_called()
            self.assertEqual(self.manager.connect({**self.body, 'base_url': 'https://jira.example'}), {'error': 'auth_required'})
        self.assertFalse(self.manager.path.exists())

    def test_real_search_uses_only_fixed_read_tool_and_minimal_task_words(self):
        self.assertTrue(self.manager.connect(self.body)['search_supported'])
        data = self.manager.discover({'agent': 'terminal', 'display_name': 'SRAM Vmin Vmax'},
                                     'private transcript that must not leave Dashboard', self.index)
        self.assertEqual([row['key'] for row in data['items']], ['SRAM-7'])
        self.assertEqual(data['items'][0]['match'], 'task')
        calls = [json.loads(line)['params'] for line in self.record.read_text().splitlines()
                 if json.loads(line)['method'] == 'tools/call']
        self.assertEqual(calls, [{'name': 'jira_search', 'arguments': {
            'jql': 'summary ~ "sram" AND summary ~ "vmin" AND summary ~ "vmax" ORDER BY updated DESC',
            'fields': 'summary,status', 'limit': 8}}])
        self.assertNotIn('private transcript', self.record.read_text())

    def test_all_agent_types_search_and_reject_unmatched_provider_results(self):
        self.connect()
        response = {'items': [{'key': 'SRAM-7', 'title': 'SRAM Vmin Vmax', 'match': 'task'},
                              {'key': 'OTHER-8', 'title': 'Unrelated', 'match': 'task'},
                              {'key': 'BAD', 'title': 'SRAM Vmin Vmax', 'match': 'task'}], 'failed': []}
        for agent in ['claude', 'codex', 'cursor', 'terminal', 'custom-agent']:
            with self.subTest(agent=agent), patch.object(jira_mcp, 'call_worker', return_value=response) as worker:
                data = self.manager.discover({'agent': agent, 'display_name': 'SRAM Vmin Vmax'}, '', self.root / agent)
                self.assertEqual([row['key'] for row in data['items']], ['SRAM-7'])
                self.assertEqual(worker.call_args.kwargs['terms'], ['sram', 'vmin', 'vmax'])

    def test_disabled_search_and_untrusted_query_text_never_call_a_tool(self):
        result = jira_mcp.call_worker({**self.server, 'search_disabled': True}, [], terms=['sram', 'vmin'])
        self.assertEqual(result['search_error'], 'unsupported_search')
        result = jira_mcp.call_worker(self.server, [], terms=['sram" OR project = PRIVATE'])
        self.assertEqual(result['search_error'], 'invalid_terms')
        calls = [json.loads(line) for line in self.record.read_text().splitlines()]
        self.assertFalse(any(row['method'] == 'tools/call' for row in calls))

    def test_search_cache_rename_explicit_refresh_and_unsupported_search(self):
        self.connect()
        run = {'display_name': 'SRAM Vmin Vmax'}
        response = {'items': [], 'failed': [], 'search_error': 'unsupported_search'}
        with patch.object(jira_mcp, 'call_worker', return_value=response) as worker:
            self.assertEqual(self.manager.discover(run, '', self.index)['search_error'], 'unsupported_search')
            self.assertEqual(self.manager.discover(run, '', self.index)['search_error'], 'unsupported_search')
            self.assertEqual(worker.call_count, 1)
            self.manager.discover(run, '', self.index, force=True)
            self.assertEqual(worker.call_count, 2)
            self.manager.discover({'display_name': 'SRAM fallout analysis'}, '', self.index)
            self.assertEqual(worker.call_count, 3)
            self.manager.discover(run, '', self.index, lookup=False)
            self.assertEqual(worker.call_count, 3)

    def test_live_local_branch_is_evidence_for_any_agent_but_ssh_never_uses_local_cwd(self):
        self.connect()
        repo = self.root / 'repo'
        subprocess.run(['git', 'init', '--quiet', '--initial-branch=fix/SRAM-9', str(repo)], check=True)
        for agent in ['terminal', 'custom-agent', 'codex']:
            with self.subTest(agent=agent), patch.object(jira_mcp, 'terminal_files', SimpleNamespace(
                    detect_environment=lambda session: {'host': '', 'cwd': str(repo)})), \
                    patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': []}) as worker:
                self.manager.discover({'agent': agent, 'tmux_session': 'fixture', 'cwd': '/stale'}, '', self.root / agent)
                self.assertEqual(worker.call_args.args[1], ['SRAM-9'])
        with patch.object(jira_mcp, 'terminal_files', SimpleNamespace(
                detect_environment=lambda session: {'host': 'remote', 'cwd': str(repo)})), \
                patch.object(jira_mcp, 'call_worker') as worker:
            self.manager.discover({'agent': 'codex', 'tmux_session': 'ssh-fixture', 'cwd': str(repo)}, '', self.root / 'ssh')
            worker.assert_not_called()
