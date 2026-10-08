"""Creation choices persist on the owning Dashboard; catalogs never run a turn."""
import asyncio
import json
from pathlib import Path
import tempfile
import httpx
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, model_catalog
from agent_orchestrator.pane_groups import PaneGroups


class SessionOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = PaneGroups(self.root)
        self.store.change({"action": "create", "name": "Project", "color": "blue"})
        self.gid = self.store.view([])["groups"][0]["id"]
        self.app = dashboard.create_app(self.root, token="test-token", ttyd_enabled=False, remote_nodes_enabled=False)

    def spawn(self, *args, **kwargs):
        return type('Result', (), {'returncode': 0, 'stdout': 'Session: orch-fixture\n', 'stderr': ''})()

    def test_creation_assigns_immediate_identity_without_session_metadata(self):
        with TestClient(self.app) as client, patch.object(dashboard.subprocess, 'run', side_effect=self.spawn):
            result = client.post('/api/create', headers={'Authorization':'Bearer test-token'}, json={
                'agent':'terminal', 'cwd':str(self.root), 'mode':'background', 'group_id':self.gid}).json()
        self.assertTrue(result['ok'])
        self.assertEqual(result['group_id'], self.gid)
        self.assertEqual(self.store.view([{'run_id':result['run_id'], 'agent':'terminal'}])['members'][result['run_id']], self.gid)

    def test_deleted_group_and_corrupt_storage_reject_before_launch(self):
        with TestClient(self.app) as client, patch.object(dashboard.subprocess, 'run') as spawn:
            for group in ['deleted', []]:
                response = client.post('/api/create', headers={'Authorization':'Bearer test-token'}, json={'group_id':group})
                self.assertEqual(response.status_code, 400)
            self.store.path.write_text('broken')
            response = client.post('/api/create', headers={'Authorization':'Bearer test-token'}, json={'group_id':self.gid})
            self.assertEqual(response.status_code, 503)
            self.assertFalse(any(str(call.args[0][0]).endswith('/run.sh') for call in spawn.call_args_list))

    def test_assignment_failure_reports_created_session_without_launch_retry(self):
        with TestClient(self.app) as client, patch.object(dashboard.subprocess, 'run', side_effect=self.spawn) as spawn, patch.object(PaneGroups, 'change', side_effect=OSError('private-error')):
            response = client.post('/api/create', headers={'Authorization':'Bearer test-token'}, json={
                'agent':'terminal','cwd':str(self.root),'mode':'background','group_id':self.gid})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('group_warning', response.json())
        self.assertNotIn('private-error', json.dumps(response.json()))
        self.assertEqual(sum(str(call.args[0][0]).endswith('/run.sh') for call in spawn.call_args_list), 1)

    def test_catalog_auth_validation_cache_and_refresh(self):
        discover = AsyncMock(return_value=[{'id':'cli-model','label':'CLI model'}])
        with TestClient(self.app) as client, patch.object(model_catalog, 'discover', discover):
            self.assertEqual(client.get('/api/models').status_code, 401)
            headers={'Authorization':'Bearer test-token'}
            self.assertEqual(client.get('/api/models?agent=terminal',headers=headers).status_code,400)
            for refresh in [False,False,True]:
                result=client.get('/api/models',headers=headers,params={'agent':'claude','cwd':str(self.root),'refresh':str(refresh).lower()})
                self.assertEqual(result.json()['models'][0]['id'],'cli-model')
            self.assertEqual(discover.await_count,2)

    def test_remote_catalog_and_creation_use_selected_node_and_dashboard_group(self):
        config=self.root/'config.json'
        config.write_text(json.dumps({'remote_nodes':[{'id':'dev','url':'http://127.0.0.1:17861','token':'node-token'}]}))
        calls=[]
        async def remote_request(method,url,**kwargs):
            path=httpx.URL(url).path
            if path in ('/api/models','/api/create'):
                calls.append((method,path,kwargs))
            payload={'models':[{'id':'remote-model','label':'Remote model'}]} if path=='/api/models' else {'ok':True,'run_id':'remote-run::task'} if path=='/api/create' else {'sessions':[]}
            return httpx.Response(200,json=payload,request=httpx.Request(method,url))
        with patch.dict('os.environ',{'ORCH_DASHBOARD_CONFIG':str(config)}):
            app=dashboard.create_app(self.root,token='test-token',ttyd_enabled=False)
        with patch.object(httpx.AsyncClient,'request',side_effect=remote_request),TestClient(app) as client:
            headers={'Authorization':'Bearer test-token'}
            models=client.get('/api/models',headers=headers,params={'agent':'codex','node_id':'dev','cwd':'/remote/project'}).json()
            result=client.post('/api/create',headers=headers,json={'node_id':'dev','group_id':self.gid,'agent':'codex','model':'remote-model','cwd':'/remote/project','mode':'iterm'}).json()
        self.assertEqual(models['models'][0]['id'],'remote-model')
        self.assertEqual(result['group_id'],self.gid)
        member={'run_id':result['run_id'],'node_id':'dev','agent':'codex'}
        self.assertEqual(self.store.view([member])['members'][result['run_id']],self.gid)
        create=next(call for call in calls if call[1]=='/api/create')[2]
        self.assertNotIn('group_id',create['json'])
        self.assertEqual(create['json']['mode'],'background')
        self.assertEqual(create['headers']['Authorization'],'Bearer node-token')
        query=next(call for call in calls if call[1]=='/api/models')[2]['params']
        self.assertEqual(query['cwd'],'/remote/project')
        self.assertEqual(query['agent'],'codex')


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def probe(self, agent, script):
        with tempfile.TemporaryDirectory() as temp:
            binary=Path(temp)/'fake-cli'
            binary.write_text('#!/usr/bin/env python3\n'+script)
            binary.chmod(0o700)
            with patch.object(model_catalog,'executable',return_value=str(binary)):
                return await model_catalog.discover(agent,temp)

    async def test_codex_protocol_only_initializes_and_lists(self):
        result=await self.probe('codex', '''import json,sys
init=json.loads(input());assert init['method']=='initialize'
print(json.dumps({'id':1,'result':{}}),flush=True)
assert json.loads(input())['method']=='initialized'
assert json.loads(input())['method']=='model/list'
print(json.dumps({'id':2,'result':{'data':[{'model':'live-model','displayName':'Live model'},{'model':'hidden','hidden':True}]}}),flush=True)
input()
''')
        self.assertEqual(result,[{'id':'live-model','label':'Live model'}])

    async def test_claude_control_init_sanitizes_account_and_never_sends_prompt(self):
        result=await self.probe('claude', '''import json,sys
assert '--no-session-persistence' in sys.argv and '--tools' in sys.argv
request=json.loads(input());assert request['type']=='control_request' and request['request']['subtype']=='initialize'
print(json.dumps({'type':'control_response','response':{'request_id':'models','response':{'account':{'token':'private'},'models':[{'value':'sonnet','displayName':'Sonnet'},{'value':'sonnet'}]}}}),flush=True)
input()
''')
        self.assertEqual(result,[{'id':'sonnet','label':'Sonnet'}])

    async def test_cursor_ansi_catalog_and_unrecognized_output(self):
        result=await self.probe('cursor', "import sys\nassert sys.argv[1:]==['--list-models']\nprint('Available models\\n\\x1b[32mcurrent-model - Current model\\x1b[0m\\nTip: --model value')\n")
        self.assertEqual(result,[{'id':'current-model','label':'Current model'}])
        with self.assertRaises(model_catalog.CatalogUnavailable):
            await self.probe('cursor', "print('private credentials: failure')\n")

    async def test_timeout_reaps_worker_and_sanitizes_errors(self):
        with patch.object(model_catalog,'QUERY_TIMEOUT',0.15):
            with self.assertRaises(model_catalog.CatalogUnavailable) as caught:
                await self.probe('cursor', "import time\ntime.sleep(60)\n")
        self.assertIn('retry',str(caught.exception))

    async def test_query_failure_is_cached_and_explicit_refresh_retries(self):
        catalog=model_catalog.ModelCatalog()
        with patch.object(model_catalog,'discover',AsyncMock(side_effect=model_catalog.CatalogUnavailable('Unavailable'))) as discover:
            self.assertEqual((await catalog.query('codex','/tmp'))['models'],[])
            await catalog.query('codex','/tmp')
            await catalog.query('codex','/tmp',True)
            self.assertEqual(discover.await_count,2)
