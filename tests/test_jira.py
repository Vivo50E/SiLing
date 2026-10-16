import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent_orchestrator import jira, dashboard
from agent_orchestrator.pane_groups import PaneGroups


class JiraTests(unittest.TestCase):
    def test_normalization_and_invalid_urls(self):
        self.assertEqual(jira.ticket_url('https://JIRA.example/jira/browse/DEMO-12?x=y#z')['url'],
                         'https://jira.example/jira/browse/DEMO-12')
        for bad in ['javascript:alert(1)', 'https://token@jira.example/browse/DEMO-1',
                    'https://jira.example/browse/DEMO-0', 'https://jira.example/browse/DEMO-1\ntext',
                    'https://jira.example/issues/DEMO-1']:
            self.assertIsNone(jira.ticket_url(bad))

    def test_collect_deduplicates_limits_and_preserves_link_label(self):
        url='https://jira.example/browse/DEMO-1'
        result=jira.collect({'linked_folders':[{'path':url,'label':'Custom title'}]},
                            f'{url}?query=yes https://jira.example/browse/DEMO-2)')
        self.assertEqual(len(result['items']),2)
        self.assertEqual(result['items'][0]['title'],'Custom title')
        self.assertEqual(result['items'][1]['source'],'output')
        self.assertEqual(jira.collect({},url+' '*262144)['items'],[])
        self.assertEqual(len(jira.collect({},' '.join(f'https://jira.example/browse/P-{i}' for i in range(1,120)))['items']),100)

    def test_group_setting_survives_rename_and_legacy_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=PaneGroups(Path(tmp))
            store.change({'action':'create','name':'A','color':'blue','color2':'#39b5a4','jira_enabled':True})
            gid=store.view([])['groups'][0]['id']
            store.change({'action':'update','group_id':gid,'name':'B','color':'pink'})
            self.assertTrue(PaneGroups(Path(tmp)).view([])['groups'][0]['jira_enabled'])
            self.assertEqual(store.view([])['groups'][0]['color2'], '#39b5a4')
            with self.assertRaises(ValueError):
                store.change({'action':'update','group_id':gid,'name':'B','color':'pink','jira_enabled':'false'})
            store.change({'action':'update','group_id':gid,'name':'B','color':'pink','jira_enabled':False})
            self.assertFalse(store.view([])['groups'][0]['jira_enabled'])

    def test_route_requires_auth_reads_log_and_terminal_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'pane.log').write_text('x'*300000+' https://jira.example/browse/LOG-1')
            run={'agent':'terminal','run_dir':tmp,'log_file':'pane.log','tmux_session':'fixture'}
            app=dashboard.create_app(root/'outputs',token='fixture',ttyd_enabled=False,remote_nodes_enabled=False)
            client=TestClient(app)
            with client, patch.object(dashboard,'_lookup_run_light',return_value=run), \
                    patch.object(dashboard,'tmux_alive',return_value=True), \
                    patch.object(dashboard,'tmux_capture_lines',return_value='https://jira.example/browse/SSH-2'):
                self.assertEqual(client.get('/api/sessions/fixture/jira').status_code,401)
                response=client.get('/api/sessions/fixture/jira',headers={'Authorization':'Bearer fixture'})
                self.assertEqual(response.status_code,200)
                self.assertEqual([i['key'] for i in response.json()['items']],['LOG-1','SSH-2'])
