import asyncio
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, jira_mcp, jira_oauth
from agent_orchestrator.jira_oauth_jobs import JiraOAuthJobs


class Store:
    def __init__(self):self.value=None
    def get(self):return self.value
    def set(self,value):self.value=dict(value)
    def delete(self):self.value=None


class OAuthFixture:
    def __init__(self):
        owner=self;self.calls=[];self.registration_denied=False;self.bad_issuer=False
        self.unsafe_endpoint=False;self.expired_refresh=False;self.callback=None;self.challenge=None
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,data,status=200,headers=None):
                raw=json.dumps(data).encode();self.send_response(status)
                for key,value in (headers or {}).items():self.send_header(key,value)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                owner.calls.append((self.path,dict(self.headers),None))
                if self.path=='/.well-known/oauth-protected-resource/mcp':
                    self.send({'resource':owner.base+'/mcp','authorization_servers':[owner.base],
                               'scopes_supported':['read:jira','write:jira']})
                elif self.path=='/.well-known/oauth-authorization-server':
                    self.send({'issuer':owner.base+'/wrong' if owner.bad_issuer else owner.base,
                        'authorization_endpoint':owner.base+'/authorize',
                        'token_endpoint':'https://untrusted.invalid/token' if owner.unsafe_endpoint else owner.base+'/token',
                        'registration_endpoint':owner.base+'/register','code_challenge_methods_supported':['S256'],
                        'token_endpoint_auth_methods_supported':['client_secret_post']})
                else:self.send({},404)
            def do_POST(self):
                data=self.rfile.read(int(self.headers.get('Content-Length','0')))
                owner.calls.append((self.path,dict(self.headers),data))
                if self.path=='/mcp':
                    if self.headers.get('Authorization') in ('Bearer fixture-access','Bearer fixture-refreshed'):
                        if owner.mcp_protocol:
                            request=json.loads(data);method=request['method']
                            if 'id' not in request:self.send({},202);return
                            if method=='initialize':result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
                            elif method=='tools/list':result={'tools':[{'name':'jira_get_issue','inputSchema':{'type':'object','properties':{'issue_key':{'type':'string'}},'required':['issue_key']}}]}
                            else:result={'content':[],'structuredContent':{'key':'DEMO-1','fields':{'summary':'Fixture','status':{'name':'Open'}}}}
                            self.send({'jsonrpc':'2.0','id':request['id'],'result':result})
                        else:self.send({'ok':True})
                    else:self.send({},401,{'WWW-Authenticate':'Bearer resource_metadata="'+owner.base+'/.well-known/oauth-protected-resource/mcp"'})
                elif self.path=='/register':
                    if owner.registration_denied:self.send({'error':'private-registration-details'},403);return
                    body=json.loads(data);owner.callback=body['redirect_uris'][0]
                    self.send({'client_id':'fixture-client','client_secret':'fixture-secret',
                               'token_endpoint_auth_method':'client_secret_post'},201)
                elif self.path=='/token':
                    args=parse_qs(data.decode())
                    if args.get('client_secret')!=['fixture-secret']:self.send({},401);return
                    if args['grant_type']==['authorization_code']:
                        actual=base64.urlsafe_b64encode(hashlib.sha256(args['code_verifier'][0].encode()).digest()).rstrip(b'=').decode()
                        if actual!=owner.challenge or args.get('code')!=['fixture-code'] or args.get('redirect_uri')!=[owner.callback]:
                            self.send({},400);return
                        self.send({'access_token':'fixture-access','refresh_token':'fixture-refresh','token_type':'Bearer','expires_in':3600})
                    else:
                        if owner.expired_refresh:self.send({'error':'private-refresh-details'},400);return
                        self.send({'access_token':'fixture-refreshed','refresh_token':'fixture-rotated','token_type':'Bearer','expires_in':3600})
                else:self.send({},404)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.browser_threads=[];self.mcp_protocol=False

    def browser(self,url,deny=False):
        query=parse_qs(urlsplit(url).query);self.challenge=query['code_challenge'][0]
        self.assertions={'method':query['code_challenge_method'][0],'scope':query['scope'][0]}
        def redirect():
            with httpx.Client(timeout=3) as client:
                bad=client.get(self.callback,params={'state':'wrong','code':'attacker-code'})
                self.bad_callback_status=bad.status_code
                good=client.get(self.callback,params={'state':query['state'][0],**({'error':'access_denied'} if deny else {'code':'fixture-code'})})
                self.callback_headers=good.headers
        thread=threading.Thread(target=redirect,daemon=True);self.browser_threads.append(thread);thread.start()

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        for t in self.browser_threads:t.join(3)


class OAuthFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture=OAuthFixture();self.addCleanup(self.fixture.close)
        self.store=Store();self.account=secrets.token_hex(16)

    def login(self):
        jira_oauth.login(self.fixture.base+'/mcp',self.account,self.fixture.browser,store=self.store)

    async def test_real_registration_pkce_callback_token_refresh_and_rotation(self):
        self.login()
        self.assertEqual(self.fixture.bad_callback_status,400)
        self.assertEqual(self.fixture.assertions,{'method':'S256','scope':'read:jira'})
        self.assertEqual(self.fixture.callback_headers['cache-control'],'no-store')
        self.assertEqual(self.store.value['access_token'],'fixture-access')
        self.store.value['expires_at']=0
        with patch.object(jira_oauth,'Keychain',return_value=self.store):
            async with httpx.AsyncClient(auth=jira_oauth.OAuthAuth(self.fixture.base+'/mcp',self.account),follow_redirects=False) as client:
                result=await client.post(self.fixture.base+'/mcp',json={})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.store.value['refresh_token'],'fixture-rotated')
        requests=[(path,headers,parse_qs(body.decode())) for path,headers,body in self.fixture.calls if path=='/token']
        self.assertEqual(requests[-1][2]['refresh_token'],['fixture-refresh'])
        self.assertTrue(all('Authorization' not in headers for _,headers,_ in requests))

    async def test_real_mcp_transport_uses_owned_oauth_account(self):
        from agent_orchestrator.jira_mcp_worker import query
        self.login();self.fixture.mcp_protocol=True;self.store.value['expires_at']=0
        with patch.object(jira_oauth,'Keychain',return_value=self.store):
            result=await query({'server':{'url':self.fixture.base+'/mcp','oauth_account':self.account},'keys':['DEMO-1']})
        self.assertEqual(result['items'],[{'key':'DEMO-1','title':'Fixture','state':'Open'}])
        self.assertEqual(self.store.value['refresh_token'],'fixture-rotated')

    async def test_successful_streaming_headers_do_not_buffer_the_event_stream(self):
        self.login()
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                raise AssertionError('OAuth must not buffer a successful MCP event stream')
                yield b''
        async def handler(request):return httpx.Response(200,headers={'Content-Type':'text/event-stream'},stream=Stream())
        with patch.object(jira_oauth,'Keychain',return_value=self.store):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),auth=jira_oauth.OAuthAuth(self.fixture.base+'/mcp',self.account)) as client:
                async with client.stream('POST',self.fixture.base+'/mcp') as response:self.assertEqual(response.status_code,200)

    async def test_401_refreshes_once_but_never_launches_an_interactive_flow(self):
        self.login();self.store.value['access_token']='expired'
        with patch.object(jira_oauth,'Keychain',return_value=self.store):
            async with httpx.AsyncClient(auth=jira_oauth.OAuthAuth(self.fixture.base+'/mcp',self.account)) as client:
                self.assertEqual((await client.post(self.fixture.base+'/mcp')).status_code,200)
        self.assertEqual(sum(path=='/register' for path,_,_ in self.fixture.calls),1)

    async def test_failed_refresh_and_resource_mismatch_do_not_leak_credentials(self):
        self.login();self.store.value['expires_at']=0;self.fixture.expired_refresh=True
        with patch.object(jira_oauth,'Keychain',return_value=self.store):
            async with httpx.AsyncClient(auth=jira_oauth.OAuthAuth(self.fixture.base+'/mcp',self.account)) as client:
                with self.assertRaisesRegex(jira_oauth.OAuthError,'auth_required'):
                    await client.post(self.fixture.base+'/mcp')
                with self.assertRaisesRegex(jira_oauth.OAuthError,'auth_required'):
                    await client.post(self.fixture.base+'/another-resource')
        self.assertFalse(any(path=='/another-resource' for path,_,_ in self.fixture.calls))

    async def test_redirects_are_not_followed_with_tokens(self):
        self.login()
        async def handler(request):return httpx.Response(302,headers={'Location':'https://untrusted.invalid/'})
        with patch.object(jira_oauth,'Keychain',return_value=self.store):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler),auth=jira_oauth.OAuthAuth(self.fixture.base+'/mcp',self.account),follow_redirects=False) as client:
                self.assertEqual((await client.post(self.fixture.base+'/mcp')).status_code,302)

    async def test_discovery_rejects_mismatched_issuer_or_cross_origin_token_endpoint(self):
        for field in ('bad_issuer','unsafe_endpoint'):
            setattr(self.fixture,field,True)
            with self.assertRaisesRegex(jira_oauth.OAuthError,'oauth_metadata_invalid'):self.login()
            setattr(self.fixture,field,False)
        self.assertFalse(any(path=='/register' for path,_,_ in self.fixture.calls))

    async def test_registration_policy_and_browser_denial_have_fixed_errors(self):
        self.fixture.registration_denied=True
        with self.assertRaisesRegex(jira_oauth.OAuthError,'oauth_registration_denied'):self.login()
        self.fixture.registration_denied=False
        with self.assertRaisesRegex(jira_oauth.OAuthError,'oauth_denied'):
            jira_oauth.login(self.fixture.base+'/mcp',self.account,lambda url:self.fixture.browser(url,deny=True),store=self.store)
        self.assertNotIn('access_token',self.store.value)

    async def test_unavailable_keychain_prevents_remote_client_registration(self):
        with patch.object(self.store,'set',side_effect=jira_oauth.KeychainError('keychain_unavailable')):
            with self.assertRaisesRegex(ValueError,'keychain_unavailable'):self.login()
        self.assertEqual(self.fixture.calls,[])


class OAuthManagerTests(unittest.TestCase):
    def test_verified_account_is_internal_and_disconnect_clears_only_owned_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'mcp.json';config.write_text(json.dumps({'mcpServers':{'jira':{'url':'https://mcp.example/mcp'}}}))
            manager=jira_mcp.JiraMCP(root/'out');body={'config_file':str(config),'server_name':'jira','base_url':'https://jira.example'}
            account=secrets.token_hex(16)
            with patch.object(jira_mcp,'call_worker',return_value={'items':[],'failed':[]}) as worker:
                status=manager.connect(body,_oauth_account=account,_expected={})
                self.assertTrue(status['enabled']);self.assertTrue(status['oauth_connected'])
                self.assertNotIn(account,json.dumps(status))
                self.assertEqual(worker.call_args.args[0]['oauth_account'],account)
            with patch('agent_orchestrator.jira_oauth_jobs.forget') as forget:
                self.assertFalse(manager.disconnect()['enabled']);forget.assert_called_once_with(account)
            self.assertNotIn('oauth_account',json.loads(manager.path.read_text()))

    def test_cancel_invalidates_inflight_verification_without_disabling_previous_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=jira_mcp.JiraMCP(Path(tmp))
            manager.path.write_text(json.dumps({'enabled':True,'connection_id':'old'}))
            manager.oauth.job={'id':secrets.token_hex(16),'state':'verifying'}
            manager.oauth.cancel()
            stored=json.loads(manager.path.read_text())
            self.assertTrue(stored['enabled']);self.assertNotEqual(stored['connection_id'],'old')
            self.assertEqual(manager.oauth.status()['state'],'cancelled')

    def test_api_requires_explicit_same_origin_local_mac_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=dashboard.create_app(Path(tmp),token='fixture',ttyd_enabled=False,remote_nodes_enabled=False)
            with TestClient(app) as client:
                path='/api/jira/mcp/oauth-start'
                self.assertEqual(client.post(path,json={}).status_code,401)
                auth={'Authorization':'Bearer fixture'}
                self.assertEqual(client.post(path,json={},headers=auth).status_code,403)
                headers={**auth,'X-Siling-Jira-MCP':'user-click'}
                self.assertEqual(client.post(path,json={},headers={**headers,'Origin':'https://untrusted.invalid'}).status_code,403)
                result=client.post(path,json={},headers=headers)
                self.assertEqual(result.json()['error'],'oauth_local_mac_required')


class OAuthJobTests(unittest.TestCase):
    def test_real_child_success_and_cancel_are_bounded_and_do_not_expose_payload(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);config=root/'mcp.json';config.write_text(json.dumps({'mcpServers':{'jira':{'url':'https://mcp.example/mcp'}}}))
                manager=jira_mcp.JiraMCP(root/'out');body={'config_file':str(config),'server_name':'jira','base_url':'https://jira.example'}
                popen=subprocess.Popen
                source='import sys,json,time;json.load(sys.stdin);print(json.dumps({"state":"waiting"}),flush=True);'+('time.sleep(120)' if cancel else 'print(json.dumps({"state":"authorized"}),flush=True)')
                def spawn(*args,**kwargs):return popen([sys.executable,'-c',source],**kwargs)
                with patch('agent_orchestrator.jira_oauth_jobs.sys.platform','darwin'), \
                        patch('agent_orchestrator.jira_oauth_jobs.subprocess.Popen',side_effect=spawn), \
                        patch.object(manager,'connect',return_value={'enabled':True}) as connect, \
                        patch('agent_orchestrator.jira_oauth_jobs.forget') as forget:
                    started=manager.oauth.start(body)
                    self.assertEqual(started['state'],'starting')
                    deadline=time.monotonic()+5
                    while manager.oauth.status()['state']=='starting' and time.monotonic()<deadline:time.sleep(.01)
                    if cancel:manager.oauth.cancel()
                    while ((manager.oauth.process is not None or manager.oauth.status()['state'] in {'starting','waiting','verifying'}) and time.monotonic()<deadline):time.sleep(.01)
                    state=manager.oauth.status()
                    self.assertEqual(state['state'],'cancelled' if cancel else 'connected')
                    self.assertNotIn('mcp.example',json.dumps(state))
                    if cancel:
                        connect.assert_not_called();self.assertTrue(forget.called)
                    else:self.assertEqual(connect.call_args.kwargs['_oauth_account'],started['id'])
