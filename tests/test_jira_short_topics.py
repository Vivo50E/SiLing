import json
import unittest
from unittest.mock import patch

from agent_orchestrator import jira, jira_mcp, jira_topics
from tests import test_jira_task_search as fixtures


class JiraShortTopicTests(unittest.TestCase):
    setUp = fixtures.JiraTaskSearchTests.setUp
    connect = fixtures.JiraTaskSearchTests.connect

    def test_current_name_keeps_short_acronyms_and_never_uses_old_task_name(self):
        for title, expected in [('NVPE-OI', ['nvpe', 'oi']), ('nvpe oi', ['nvpe', 'oi']),
                                ('AI UI', ['ai', 'ui']), ('Fix in NVPE OI', ['nvpe', 'oi'])]:
            with self.subTest(title=title):
                self.assertEqual(jira.task_terms({'display_name': title, 'task': 'NVPE-ATE'}), expected)
        for title in ['interactive', 'NVPE', 'fix']:
            run = {'display_name': title, 'task': 'SRAM voltage'}
            self.assertEqual(jira.task_terms(run), [], 'Do not use an obsolete task name')
        self.assertEqual(jira.task_terms({'display_name': ' ', 'label': 'NVPE OI'}), ['nvpe', 'oi'])

    def test_real_worker_searches_short_terms_and_excludes_old_name_matches(self):
        self.server['env']['FIXTURE_SHORT_TOPIC'] = '1'
        self.config.write_text(json.dumps({'mcpServers': {'jira': self.server}}))
        self.assertTrue(self.manager.connect(self.body)['search_supported'])
        data = self.manager.discover({'display_name': 'NVPE-OI', 'task': 'NVPE-ATE'}, '', self.index)
        self.assertEqual([i['key'] for i in data['items']], ['DEMO-7'])
        calls = [json.loads(line) for line in self.record.read_text().splitlines()]
        search = [c['params']['arguments'] for c in calls
                  if c['method'] == 'tools/call' and c['params']['name'] == 'jira_search']
        self.assertEqual(search[0]['jql'], 'summary ~ "nvpe" AND summary ~ "oi" ORDER BY updated DESC')

    def test_real_worker_accepts_short_ai_keywords_and_still_rejects_injection(self):
        self.server['env']['FIXTURE_SHORT_TOPIC'] = '1'
        result = jira_mcp.call_worker(self.server, [], topics=[['nvpe', 'oi']])
        self.assertNotIn('search_error', result)
        self.assertEqual([i['key'] for i in result['items']], ['DEMO-7'])
        result = jira_mcp.call_worker(self.server, [], topics=[['nvpe', 'o"']])
        self.assertEqual(result['search_error'], 'invalid_terms')

    def test_unusable_current_name_reports_skipped_without_querying_old_metadata(self):
        self.connect()
        with patch.object(jira_mcp, 'call_worker') as worker:
            result = self.manager.discover({'display_name': 'interactive', 'task': 'OLD-9'}, '', self.index)
            worker.assert_not_called()
        self.assertEqual(result.get('search_skipped'), 'no_keywords')
        self.assertNotIn('search_error', result)

    def test_empty_model_plan_is_distinct_and_retries_after_cooldown(self):
        self.connect()
        run = {'display_name': 'interactive', 'task': 'SRAM voltage'}
        with patch.object(jira_topics, 'plan', return_value=[]) as model, \
                patch.object(jira_mcp, 'call_worker') as worker, \
                patch.object(jira_mcp.time, 'time', return_value=1000) as clock:
            first = self.manager.discover(run, '', self.index, topic=True)
            self.assertEqual(first.get('topic_error'), 'topic_no_keywords')
            self.assertEqual(first.get('search_skipped'), 'no_keywords')
            self.manager.discover(run, '', self.index, topic=True, force=True)
            self.assertEqual(model.call_count, 1)
            clock.return_value = 1601
            self.manager.discover(run, '', self.index, topic=True)
            self.assertEqual(model.call_count, 2)
            worker.assert_not_called()

    def test_old_empty_topic_cache_is_invalidated_and_literal_lookup_still_runs(self):
        self.connect()
        run = {'display_name': 'NVPE-OI', 'task': 'NVPE-ATE'}
        self.index.mkdir()
        identity = jira_mcp.fingerprint({'context': jira_topics.context(run), 'version': 1})
        (self.index / 'jira-topics.json').write_text(json.dumps(
            {'identity': identity, 'topics': [], 'error': '', 'at': 1000}))
        with patch.object(jira_topics, 'plan', return_value=[]) as model, \
                patch.object(jira_mcp, 'call_worker', return_value={'items': [], 'failed': []}) as worker:
            data = self.manager.discover(run, '', self.index, topic=True)
        model.assert_called_once()
        self.assertEqual(worker.call_args.kwargs['terms'], ['nvpe', 'oi'])
        self.assertNotIn('topic_error', data, 'A valid literal search may run without AI expansion')
        self.assertNotIn('search_skipped', data)

    def test_topic_context_uses_the_same_current_nonempty_name(self):
        run = {'display_name': '   ', 'label': 'NVPE OI', 'task': 'NVPE ATE'}
        self.assertEqual(json.loads(jira_topics.context(run))['task'], 'NVPE OI')
