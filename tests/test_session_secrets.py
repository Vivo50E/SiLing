from contextlib import ExitStack
import argparse
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, cli
from agent_orchestrator.session_secrets import SessionSecrets, SessionKeychain


class MemoryStore:
    entries = {}
    def __init__(self, account): self.account = account
    def set(self, value): self.entries[self.account] = value
    def get(self): return self.entries.get(self.account)
    def delete(self): self.entries.pop(self.account, None)


class SessionSecretTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        MemoryStore.entries = {}
        self.service = SessionSecrets(store=MemoryStore)
        self.addCleanup(self.service.close)
        self.spec = {'name':'TEST_KEY', 'cwd':self.temp.name,
                     'argv':[sys.executable, '-c', 'import os,hashlib; assert hashlib.sha256(os.environ["TEST_KEY"].encode()).hexdigest() == "0248f56577e62962fd6ae2f4d93b4ae9323f4976469d53ffa6953d3bd0f1664d"; print(os.environ["TEST_KEY"])']}

    def finish(self, row):
        self.service.requests[row['id']]['worker'].join(5)
        return next(r for r in self.service.list('a') if r['id'] == row['id'])

    def test_explicit_approval_env_only_no_output_or_unrelated_credentials(self):
        spec = {**self.spec, 'argv':[sys.executable, '-c', 'import os,sys,hashlib; assert hashlib.sha256(os.environ["TEST_KEY"].encode()).hexdigest() == "0248f56577e62962fd6ae2f4d93b4ae9323f4976469d53ffa6953d3bd0f1664d"; assert "UNRELATED_TOKEN" not in os.environ; print(os.environ["TEST_KEY"]); sys.stderr.write(os.environ["TEST_KEY"])']}
        with patch.dict(os.environ, {'UNRELATED_TOKEN':'private-other'}):
            row = self.service.request('a', spec)
            self.assertEqual(row['state'], 'pending')
            self.assertEqual(self.service.list('b'), [])
            self.assertEqual(os.listdir(self.temp.name), [])
            self.service.approve('a', row['id'], {'source':'input','value':'fixture-value'})
            result = self.finish(row)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['exit_code'], 0)
        self.assertNotIn("fixture-value", json.dumps(result))
        self.assertNotIn('stdout', result)
        self.assertNotIn('value', result)
        self.assertEqual(os.listdir(self.temp.name), [])
        with self.assertRaises(ValueError):
            self.service.approve('a', row['id'], {'source':'input','value':'fixture-value'})

    def test_request_validation_scope_dedup_and_no_overrides(self):
        row = self.service.request('a', self.spec)
        self.assertEqual(self.service.request('a', self.spec)['id'], row['id'])
        with self.assertRaises(ValueError): self.service.approve('b', row['id'], {'source':'input','value':'secret'})
        with self.assertRaises(ValueError): self.service.request('a', {**self.spec,'value':'secret'})
        with self.assertRaises(ValueError): self.service.approve('a', row['id'], {'source':'input','value':'secret','argv':['/bin/echo']})
        for change in ({'name':'X=Y'}, {'argv':['echo']}, {'cwd':'relative'}, {'timeout':999}, {'argv':[]}):
            with self.assertRaises(ValueError): self.service.request('a', {**self.spec, **change})

    def test_keychain_opt_in_reuse_and_delete_scoped_by_directory_and_name(self):
        row = self.service.request('a', self.spec)
        self.service.approve('a', row['id'], {'source':'input','value':'fixture-value'})
        self.finish(row)
        self.assertEqual(MemoryStore.entries, {})
        second = self.service.request('a', self.spec)
        self.assertTrue(second['session_value_available'])
        self.service.approve('a', second['id'], {'source':'session','save':True})
        self.finish(second)
        self.assertEqual(len(MemoryStore.entries), 1)
        third = self.service.request('b', self.spec)
        self.assertFalse(third['session_value_available'])
        with self.assertRaises(ValueError): self.service.approve('b', third['id'], {'source':'session'})
        self.service.approve('b', third['id'], {'source':'keychain'})
        self.service.requests[third['id']]['worker'].join(5)
        self.service.forget('b', third['id'], saved=True)
        self.assertEqual(MemoryStore.entries, {})
        other = self.service.request('c', {**self.spec,'name':'OTHER_KEY'})
        with self.assertRaises(ValueError): self.service.approve('c', other['id'], {'source':'keychain'})
        self.assertNotEqual(SessionKeychain.service, 'SiLing.JiraMCP.OAuth.v1')

    def test_keychain_failure_never_executes_or_falls_back(self):
        row = self.service.request('a', self.spec)
        with patch.object(MemoryStore,'set',side_effect=ValueError('fixture-private-error')):
            with self.assertRaises(ValueError): self.service.approve('a', row['id'], {'source':'input','value':'fixture-value','save':True})
        self.assertEqual(self.service.list('a')[0]['state'], 'pending')
        self.assertEqual(self.service.values, {})

    def test_cancel_timeout_shutdown_and_expiry(self):
        row = self.service.request('a', self.spec)
        self.service.cancel('a',row['id'])
        with self.assertRaises(ValueError): self.service.approve('a', row['id'], {'source':'input','value':'secret'})
        row = self.service.request('a', {**self.spec,'argv':[sys.executable,'-c','import time; time.sleep(10)'],'timeout':1})
        self.service.approve('a',row['id'], {'source':'input','value':'secret'})
        self.assertEqual(self.finish(row)['state'], 'timed_out')
        retained = next(iter(self.service.values.values()))[0]
        self.service.clock = lambda: time.time()+7200
        self.assertEqual(self.service.list(), [])
        self.assertEqual(bytes(retained), b'\0'*6)
        self.service.close()
        self.assertEqual(self.service.values, {})

    def test_revoke_kills_running_command_and_erases_session(self):
        row = self.service.request('a', {**self.spec,'argv':[sys.executable,'-c','import time; time.sleep(10)']})
        self.service.approve('a',row['id'], {'source':'input','value':'secret'})
        worker = self.service.requests[row['id']]['worker']
        self.service.revoke_run('a')
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.service.list('a'), [])
        self.assertEqual(self.service.values, {})

    def test_api_transport_auth_same_origin_approval_and_safe_errors(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0'}))
            lookup = stack.enter_context(patch.object(dashboard,'_lookup_run_light',return_value={'tmux_session':'fixture'}))
            stack.enter_context(patch.object(dashboard,'tmux_alive',return_value=True))
            stack.enter_context(patch.object(dashboard,'SessionSecrets',return_value=self.service))
            app = dashboard.create_app(Path(self.temp.name), token='fixture-auth', ttyd_enabled=False, remote_nodes_enabled=False)
            client = stack.enter_context(TestClient(app,base_url='https://testserver'))
            auth = {'Authorization':'Bearer fixture-auth'}
            base = '/api/sessions/a/secret-requests'
            self.assertEqual(client.get(base).status_code,401)
            row = client.post(base,json=self.spec,headers=auth).json()['request']
            self.assertEqual(client.get('/api/secret-requests',headers=auth).headers['cache-control'],'no-store')
            url = base+'/'+row['id']+'/approve'
            value = {'source':'input','value':'fixture-value'}
            self.assertEqual(client.post(url,json=value,headers=auth).status_code,403)
            headers = {**auth,'Origin':'https://testserver','X-Siling-User-Intent':'approve-secret'}
            self.assertEqual(client.post(url,json=value,headers={**headers,'Origin':'https://evil.test'}).status_code,403)
            response = client.post(url,json=value,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            self.finish(row)
            self.assertEqual(client.post(url,json=value,headers=headers).status_code,409)
            response = client.post(base,content=b'{broken fixture-private',headers=auth)
            self.assertNotIn('fixture-private',response.text)
            self.assertEqual(response.status_code,400)
            insecure = stack.enter_context(TestClient(app,base_url='http://testserver'))
            self.assertEqual(insecure.get('/api/secret-requests',headers=auth).status_code,403)
            lookup.return_value = None
            self.assertEqual(client.get(base,headers=auth).status_code,404)
            self.assertEqual(self.service.values,{})

    def test_cli_request_sends_no_value_and_prints_status_only(self):
        args = argparse.Namespace(run_id='a', dashboard_url='', secret_action='request', name='TEST_KEY',
                                  cwd=self.temp.name, command=['--','/usr/bin/true'],reason='test',timeout=60)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'request':{'id':'a'*32,'state':'pending','value':'unexpected-private'}}).encode()
        with patch.object(cli,'_dashboard_api_base',return_value='http://127.0.0.1:7860'), patch.object(cli,'dashboard_token',return_value=''), patch.object(cli,'build_opener') as build, patch('sys.stdout',new_callable=io.StringIO) as output:
            build.return_value.open.return_value = response
            cli.cmd_secret_request(args)
            request = build.return_value.open.call_args.args[0]
            self.assertNotIn('value',json.loads(request.data))
            self.assertNotIn('unexpected-private',output.getvalue())
            self.assertEqual(json.loads(request.data)['argv'], ['/usr/bin/true'])

    def test_idle_lifecycle_reaps_ended_session_and_pending_expiry(self):
        now = [1000]
        service = SessionSecrets(store=MemoryStore, clock=lambda:now[0], alive=lambda _:False)
        self.addCleanup(service.close)
        service.request('a', self.spec)
        now[0] += 901
        self.assertEqual(service.list(), [])
        service.request('a', self.spec)
        service.start()
        for _ in range(65):
            if not service.list(): break
            time.sleep(.1)
        self.assertEqual(service.list(), [])

    def test_remote_command_requests_never_forward_to_wrong_host(self):
        import httpx
        from unittest.mock import AsyncMock
        from agent_orchestrator.remote_nodes import RemoteNodeRegistry, RemoteNodeSettings, qualify_run_id
        from urllib.parse import quote
        with ExitStack() as stack:
            registry = RemoteNodeRegistry([RemoteNodeSettings(id='fixture-node',label='Fixture',url='https://node.invalid',token='fixture-auth')])
            stack.enter_context(patch.object(dashboard,'RemoteNodeRegistry',return_value=registry))
            stack.enter_context(patch.object(registry,'start'))
            stack.enter_context(patch.object(registry,'stop'))
            upstream = stack.enter_context(patch.object(httpx.AsyncClient,'request',new_callable=AsyncMock))
            app = dashboard.create_app(Path(self.temp.name),token='fixture-auth',ttyd_enabled=False)
            client = stack.enter_context(TestClient(app,base_url='https://testserver'))
            run_id = quote(qualify_run_id('fixture-node','fixture'),safe='')
            response = client.post('/api/sessions/'+run_id+'/secret-requests',json=self.spec,headers={'Authorization':'Bearer fixture-auth'})
            self.assertEqual(response.status_code,409)
            upstream.assert_not_awaited()
