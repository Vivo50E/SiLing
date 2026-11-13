import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent_orchestrator import jira_mcp, jira_topics
from tests import test_jira_task_search as fixtures


class JiraTopicPlanTests(unittest.TestCase):
    def test_context_only_uses_bounded_metadata_and_skips_suspected_secrets(self):
        run = {'display_name': '分析 SRAM 电压边界', 'initial_prompt': 'Find voltage fallout',
               'transcript': 'private conversation', 'cwd': '/private/path'}
        text = jira_topics.context(run)
        self.assertEqual(json.loads(text), {'task': run['display_name'], 'description': run['initial_prompt']})
        self.assertNotIn('private', text)
        for value in ['token=credential', 'Bearer credential', 'https://private.example', 'A' * 45]:
            self.assertEqual(jira_topics.context({**run, 'initial_prompt': value}), '')
        self.assertEqual(len(json.loads(jira_topics.context({'display_name': 'SRAM analysis', 'initial_prompt':'y '*2000}))['description']), 2000)

    def test_model_has_no_tools_and_validates_structured_output(self):
        def invoke(argv, **kwargs):
            self.assertEqual(argv[argv.index('--tools') + 1], '')
            self.assertEqual(argv[argv.index('--mcp-config') + 1], '{"mcpServers":{}}')
            self.assertEqual(argv[argv.index('--max-budget-usd') + 1], '0.10')
            self.assertIn('--no-session-persistence', argv)
            self.assertIn('--disable-slash-commands', argv)
            self.assertEqual(json.loads(argv[argv.index('--settings') + 1]), {'disableAllHooks': True})
            self.assertEqual(kwargs['timeout'], 25)
            self.assertTrue(Path(kwargs['cwd']).is_dir())
            kwargs['stdout'].write(json.dumps({'structured_output': {'topics': [['sram', 'voltage']]}}).encode())
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(jira_topics, 'resolve_agent_cli', return_value='/fixture/claude'), \
                patch.object(jira_topics.subprocess, 'run', side_effect=invoke):
            self.assertEqual(jira_topics.plan('fixture'), [['sram', 'voltage']])
        for topics in [[['sram']], [['sram', 'voltage" OR project=X']], [['sram', 'sram']], 'untrusted', [['sram', 'voltage']]*4]:
            self.assertFalse(jira_topics.valid_topics(topics))
        self.assertTrue(jira_topics.valid_topics([]))


class JiraTopicDiscoveryTests(unittest.TestCase):
    setUp = fixtures.JiraTaskSearchTests.setUp
    connect = fixtures.JiraTaskSearchTests.connect
    def test_opt_in_semantic_plan_searches_without_keys_and_persists_reason(self):
        self.assertTrue(self.manager.connect(self.body)['search_supported'])
        run = {'agent': 'custom-agent', 'display_name': '电压边界分析', 'initial_prompt': 'Analyze SRAM voltage extremes'}
        with patch.object(jira_topics, 'plan', return_value=[['sram', 'vmin'], ['sram', 'vmax']]) as model:
            data = self.manager.discover(run, 'private transcript', self.index, topic=True)
            self.assertEqual([row['key'] for row in data['items']], ['SRAM-7'])
            self.assertEqual(data['items'][0]['match'], 'topic')
            self.assertEqual(data['items'][0]['topic_terms'], ['sram', 'vmin'])
            self.manager.discover(run, '', self.index, force=True, topic=True)
            self.assertEqual(model.call_count, 1, 'Refresh must not incur another model charge')
        calls = [json.loads(line) for line in self.record.read_text().splitlines()]
        searches = [c['params']['arguments'] for c in calls if c['method'] == 'tools/call' and c['params']['name'] == 'jira_search']
        self.assertIn('(summary ~ "sram" AND summary ~ "vmin") OR (summary ~ "sram" AND summary ~ "vmax")', searches[0]['jql'])
        self.assertNotIn('Analyze SRAM', self.record.read_text(), 'Only keywords reach Jira')
        self.assertNotIn('private transcript', self.record.read_text())

    def test_model_is_opt_in_and_independent_of_explicit_keys(self):
        self.connect()
        run = {'display_name':'电压边界分析'}
        with patch.object(jira_topics, 'plan', return_value=[['sram', 'voltage']]) as model, \
                patch.object(jira_mcp, 'call_worker', return_value={'items':[], 'failed':[]}) as worker:
            self.manager.discover(run, '', self.index)
            model.assert_not_called()
            self.manager.discover(run, '', self.index, lookup=False, topic=True)
            model.assert_not_called()
            self.manager.discover(run, 'EXISTING-1', self.index, topic=True)
            self.assertEqual(worker.call_args.args[1], ['EXISTING-1'])
            self.assertEqual(worker.call_args.kwargs['topics'], [['sram','voltage']])
            model.assert_called_once()

    def test_failures_cool_down_and_renaming_replans_without_storing_prompts(self):
        self.connect()
        run = {'display_name':'电压边界分析', 'initial_prompt':'fixture task description'}
        with patch.object(jira_topics, 'plan', side_effect=ValueError('private provider error')) as model, \
                patch.object(jira_mcp, 'call_worker', return_value={'items':[], 'failed':[]}):
            first = self.manager.discover(run, '', self.index, topic=True)
            self.assertEqual(first['topic_error'], 'topic_model_failed')
            self.manager.discover(run, '', self.index, force=True, topic=True)
            self.assertEqual(model.call_count, 1)
            self.manager.discover({**run, 'display_name':'电压极值分析'}, '', self.index, topic=True)
            self.assertEqual(model.call_count, 2)
        cache = (self.index / 'jira-topics.json').read_text()
        self.assertNotIn('fixture task description', cache)
        self.assertNotIn('private provider error', cache)

    def test_parent_rejects_unmatched_topics_and_does_not_run_model_for_unsupported_search(self):
        self.connect()
        response = {'items':[{'key':'OTHER-8','title':'Unrelated fix','match':'topic'}], 'failed':[]}
        with patch.object(jira_topics, 'plan', return_value=[['sram','voltage']]), \
                patch.object(jira_mcp, 'call_worker', return_value=response):
            result = self.manager.discover({'display_name':'电压边界分析'}, '', self.index, topic=True)
            self.assertEqual(result['items'], [])
        cfg=json.loads(self.manager.path.read_text());cfg['search_supported']=False
        self.manager.path.write_text(json.dumps(cfg))
        with patch.object(jira_topics, 'plan') as model:
            self.manager.discover({'display_name':'电压边界分析'}, '', self.index, topic=True)
            model.assert_not_called()

    def test_busy_model_does_not_block_or_call_a_second_model(self):
        self.connect()
        with self.manager.topic_slot, patch.object(jira_topics, 'plan') as model:
            result = self.manager.discover({'display_name':'电压边界分析'}, '', self.index, topic=True)
            self.assertEqual(result['topic_error'], 'topic_busy')
            model.assert_not_called()

    def test_real_worker_rejects_model_injected_jql(self):
        result = jira_mcp.call_worker(self.server, [], topics=[['sram', 'x" OR project=SECRET']])
        self.assertEqual(result['search_error'], 'invalid_terms')
        calls = [json.loads(line) for line in self.record.read_text().splitlines()]
        self.assertFalse(any(c['method']=='tools/call' for c in calls))

    def test_cached_topic_reason_survives_key_only_status_refresh(self):
        self.connect()
        run={'display_name':'电压边界分析'}
        with patch.object(jira_topics, 'plan', return_value=[['sram','voltage']]), \
                patch.object(jira_mcp, 'call_worker', return_value={'items':[
                    {'key':'SRAM-7', 'title':'SRAM voltage analysis', 'match':'topic'}], 'failed':[]}):
            self.manager.discover(run, '', self.index, topic=True)
        with patch.object(jira_mcp, 'call_worker', return_value={'items':[
                {'key':'SRAM-7', 'title':'SRAM voltage analysis', 'state':'Done'}], 'failed':[]}):
            result=self.manager.discover(run, '', self.index, force=True)
            self.assertEqual(result['items'][0]['match'], 'topic')
            self.assertEqual(result['items'][0]['topic_terms'], ['sram','voltage'])
            self.assertEqual(result['items'][0]['state'], 'Done')

    def test_disconnect_during_inference_never_starts_a_new_provider_query(self):
        self.connect()
        def disconnect(text):
            self.manager.disconnect()
            return [['sram','voltage']]
        with patch.object(jira_topics, 'plan', side_effect=disconnect), \
                patch.object(jira_mcp, 'call_worker') as worker:
            result = self.manager.discover({'display_name':'电压边界分析'}, '', self.index, topic=True)
            self.assertEqual(result['mcp_error'], 'config_changed')
            worker.assert_not_called()
