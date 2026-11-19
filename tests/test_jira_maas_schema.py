import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sys
import unittest
from unittest.mock import patch

from agent_orchestrator import jira_mcp, jira_tools, jira_topics


class MaaSSchemaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.record = self.root / 'calls.jsonl'
        self.server = {'command': sys.executable,
                       'args': [str(Path(__file__).parent / 'fixtures' / 'jira_mcp_server.py')],
                       'env': {'FIXTURE_MAAS': '1', 'FIXTURE_SEARCH': '1', 'FIXTURE_RECORD': str(self.record)}}
        self.config = self.root / 'mcp.json'
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        self.manager = jira_mcp.JiraMCP(self.root / 'outputs')
        self.body = {'config_file': str(self.config), 'server_name': 'jira', 'base_url': 'https://jira.example'}

    def calls(self):
        return [json.loads(line)['params'] for line in self.record.read_text().splitlines()
                if json.loads(line)['method'] == 'tools/call']

    def test_real_maas_issue_id_nullable_field_array_and_data_envelope(self):
        response = jira_mcp.call_worker(self.server, ['DEMO-1'])
        self.assertNotIn('error', response)
        self.assertEqual(response['items'], [{'key': 'DEMO-1', 'title': 'Fixture ticket <img src=x>', 'state': 'In Progress'}])
        self.assertEqual(self.calls(), [{'name': 'jira_get_issue', 'arguments': {
            'issue_id': 'DEMO-1', 'fields': ['summary', 'status']}}])
        self.assertTrue(response['search_supported'])
        self.assertTrue(response['search_project_required'])

    def test_real_maas_search_top_k_array_project_and_local_identity_checks(self):
        response = jira_mcp.call_worker({**self.server, 'search_project': 'SRAM'}, [], terms=['sram', 'vmin'])
        self.assertEqual([row['key'] for row in response['items']], ['SRAM-7'])
        self.assertEqual(self.calls(), [{'name': 'jira_search', 'arguments': {
            'jql': 'project = "SRAM" AND (summary ~ "sram" AND summary ~ "vmin") ORDER BY updated DESC',
            'fields': ['summary', 'status'], 'top_k': 8}}])
        response = jira_mcp.call_worker({**self.server, 'search_project': 'OTHER'}, [], terms=['sram', 'vmin'])
        self.assertEqual(response['items'], [], 'A provider cannot attach a matching title from outside the selected project')

    def test_missing_project_keeps_key_lookup_but_never_runs_unscoped_search(self):
        response = jira_mcp.call_worker(self.server, ['DEMO-1'], topics=[['sram', 'vmin']])
        self.assertEqual(response['search_error'], 'project_required')
        self.assertEqual(len(response['items']), 1)
        self.assertEqual([call['name'] for call in self.calls()], ['jira_get_issue'])

    def test_unknown_required_argument_and_failure_envelope_fail_closed(self):
        response = jira_mcp.call_worker({**self.server, 'env': {**self.server['env'], 'FIXTURE_UNKNOWN_REQUIRED': '1'}}, ['DEMO-1'])
        self.assertEqual(response, {'error': 'unsupported_tool'})
        self.assertEqual(self.calls(), [])
        response = jira_mcp.call_worker({**self.server, 'env': {**self.server['env'], 'FIXTURE_FAILURE_ENVELOPE': '1'}}, ['DEMO-1'])
        self.assertEqual(response['items'], [])
        self.assertEqual(response['failed'], ['DEMO-1'])
        self.assertNotIn('private-provider', json.dumps(response))

    def test_project_input_is_normalized_and_project_url_is_usable(self):
        self.assertEqual(jira_mcp.connection_scope('https://jira.example/jira/software/c/projects/DEMO/boards/1'), ('https://jira.example', 'DEMO'))
        self.assertEqual(jira_mcp.connection_scope('https://jira.example/jira/projects/DEMO'), ('https://jira.example/jira', 'DEMO'))
        self.assertEqual(jira_mcp.connection_scope('https://jira.example', 'demo'), ('https://jira.example', 'DEMO'))
        for project in ['X" OR project=PRIVATE', '../x', 1, 'x' * 33]:
            with self.assertRaises(ValueError):
                jira_mcp.connection_scope('https://jira.example', project)
        with self.assertRaises(ValueError):
            jira_mcp.connection_scope('https://jira.example/projects/DEMO', 'OTHER')

    def test_connect_persists_scope_and_discovery_passes_it_to_the_worker(self):
        status = self.manager.connect({**self.body, 'base_url': 'https://jira.example/jira/software/c/projects/SRAM'})
        self.assertTrue(status['enabled'])
        self.assertEqual(status['project_key'], 'SRAM')
        self.assertEqual(status['base_url'], 'https://jira.example')
        data = self.manager.discover({'display_name': 'SRAM Vmin Vmax'}, '', self.root / 'index')
        self.assertEqual([row['key'] for row in data['items']], ['SRAM-7'])
        self.assertEqual(data['items'][0]['url'], 'https://jira.example/browse/SRAM-7')

    def test_missing_project_does_not_spend_a_model_call(self):
        self.assertTrue(self.manager.connect(self.body)['enabled'])
        with patch.object(jira_topics, 'plan') as model:
            data = self.manager.discover({'display_name': 'SRAM Vmin Vmax'}, '', self.root / 'index', topic=True)
        model.assert_not_called()
        self.assertEqual(data['search_error'], 'project_required')
        self.assertEqual(self.calls(), [])

    def test_project_change_invalidates_search_cache_and_parent_rejects_outside_project(self):
        for project in ('SRAM', 'OTHER'):
            with patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': [], 'search_supported': True}):
                self.manager.connect({**self.body, 'project_key': project})
            response = {'items': [{'key': 'SRAM-7', 'title': 'SRAM Vmin Vmax', 'match': 'task'}], 'failed': []}
            with patch.object(jira_mcp, 'call_worker', return_value=response) as worker:
                result = self.manager.discover({'display_name': 'SRAM Vmin Vmax'}, '', self.root / project)
            worker.assert_called_once()
            self.assertEqual(len(result['items']), 1 if project == 'SRAM' else 0)

    def test_adapters_do_not_guess_schema_types_or_accept_ambiguous_identifiers(self):
        tool = lambda props, required: SimpleNamespace(inputSchema={'properties': props, 'required': required})
        self.assertIsNone(jira_tools.issue_arguments(tool({'issue_id': {'type': 'integer'}}, ['issue_id']), 'DEMO-1'))
        self.assertIsNone(jira_tools.issue_arguments(tool({'issue_id': {'type': 'string'}, 'issue_key': {'type': 'string'}}, []), 'DEMO-1'))
        self.assertIsNone(jira_tools.issue_arguments(tool({'issue_id': {'type': 'string'}, 'fields': {'type': 'object'}}, []), 'DEMO-1'))
        self.assertEqual(jira_tools.issue_arguments(tool({'issue_id': {'type': 'string'}, 'page': {'type': 'integer'},
            'expand_comments': {'type': 'boolean'}}, ['issue_id', 'page']), 'DEMO-1'),
            {'issue_id': 'DEMO-1', 'page': 1, 'expand_comments': False})

    def test_project_cache_scope_changes_and_invalid_projects_do_not_query_a_worker(self):
        index = self.root / 'same-index'
        for project in ('SRAM', 'OTHER'):
            with patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': [], 'search_supported': True}):
                self.manager.connect({**self.body, 'project_key': project})
            with patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': []}) as worker:
                self.manager.discover({'display_name': 'SRAM Vmin Vmax'}, '', index)
                worker.assert_called_once()
                self.assertEqual(worker.call_args.args[0]['search_project'], project)
        with patch.object(jira_mcp, 'call_worker') as worker:
            result = self.manager.connect({**self.body, 'project_key': 'bad" OR anything'})
            self.assertEqual(result, {'error': 'invalid_project'})
            worker.assert_not_called()

    def test_outer_failure_envelope_cannot_be_overridden_by_a_nested_result(self):
        from agent_orchestrator.jira_mcp_worker import result_data
        result = SimpleNamespace(isError=False, content=[], structuredContent={
            'success': False, 'data': None, 'result': {'key': 'DEMO-1', 'title': 'Misleading'}})
        self.assertIsNone(result_data(result))
