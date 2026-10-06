from contextlib import ExitStack
import argparse
import io
import json
import os
from pathlib import Path
import ssl
import http.server
import shutil
import subprocess
import threading
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from agent_orchestrator import cli, dashboard
from agent_orchestrator.secret_broker import SecretBroker


class SecretBrokerTests(unittest.TestCase):
    def setUp(self):
        self.broker = SecretBroker()
        self.addCleanup(self.broker.close)
        self.key = 'fixture-broker-private-123456'
        self.spec = {'name':'deploy','url':'https://api.example.test/deploy','method':'POST',
                     'auth':'bearer','body':'{"action":"deploy"}','value':self.key,'ttl':900}

    def test_metadata_scope_no_persistence_and_immutable_binding(self):
        result = self.broker.register('pane-a', self.spec)
        self.assertNotIn(self.key, json.dumps(result))
        self.assertNotIn('value', result)
        self.assertEqual(self.broker.list('pane-b'), [])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.broker.register('pane-a', {**self.spec,'url':'https://attacker.example.test/'})
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.broker.call('pane-b','deploy')
        self.assertEqual(self.broker.list('pane-a')[0]['url'], self.spec['url'])
        self.assertNotIn(self.key, repr(self.broker.operations['pane-a','deploy']))

    def test_fixed_authenticated_request_withholds_echoes_headers_redirects_and_errors(self):
        self.broker.register('pane-a', self.spec)
        for status in (200,302,401,500):
            with self.subTest(status=status), patch('http.client.HTTPSConnection') as factory:
                connection = factory.return_value
                response = connection.getresponse.return_value
                response.status = status
                response.read.return_value = self.key.encode()
                response.getheaders.return_value = [('Location','https://attacker.example.test/'+self.key)]
                result = self.broker.call('pane-a','deploy')
                self.assertEqual(result, {'name':'deploy','http_status':status,'ok':status==200,'response_body_withheld':True})
                response.read.assert_not_called(); response.getheaders.assert_not_called()
                connection.request.assert_called_once_with('POST','/deploy',body=b'{"action":"deploy"}',
                    headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json','Accept':'application/json'})
                connection.close.assert_called_once()
                context = factory.call_args.kwargs['context']
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(context.check_hostname)
        with patch('http.client.HTTPSConnection') as factory:
            factory.return_value.request.side_effect = RuntimeError(self.key)
            with self.assertRaises(ValueError) as error:
                self.broker.call('pane-a','deploy')
            self.assertNotIn(self.key, str(error.exception))
            self.assertIsNone(error.exception.__cause__)
            factory.return_value.request.assert_called_once()  # no replay

    def test_invalid_destinations_controls_and_embedded_keys_never_register(self):
        invalid = [{'url':'http://api.example.test/'}, {'url':'https://user:password@api.example.test/'},
                   {'url':'https://api.example.test/?key=fixture'}, {'url':'https://api.example.test/#fragment'},
                   {'url':'https:///path'}, {'value':self.key+'\n'}, {'method':'CONNECT'}, {'ttl':True},
                   {'body':self.key}, {'url':'https://api.example.test/'+self.key}, {'headers':{}},
                   {'method':'GET','body':'{}'}]
        for change in invalid:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    self.broker.register('pane-a', {**self.spec,**change})
        self.assertEqual(self.broker.list('pane-a'), [])

    def test_expiry_revoke_shutdown_and_duplicate_inflight_calls(self):
        current = [1000.0]
        self.broker.clock = lambda:current[0]
        self.broker.register('pane-a',self.spec)
        operation = self.broker.operations['pane-a','deploy']
        operation.lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'already running'):
                self.broker.call('pane-a','deploy')
        finally:
            operation.lock.release()
        current[0] += 901
        self.assertEqual(self.broker.list('pane-a'), [])
        self.assertFalse(any(operation.value))
        self.broker.register('pane-a',self.spec)
        second = self.broker.operations['pane-a','deploy']
        self.broker.revoke_run('pane-a')
        self.assertFalse(any(second.value))
        self.broker.register('pane-a',self.spec)
        third = self.broker.operations['pane-a','deploy']
        self.broker.close()
        self.assertFalse(any(third.value))
        with self.assertRaisesRegex(ValueError,'shutting down'):
            self.broker.register('pane-a',self.spec)

    def test_idle_expired_credentials_are_erased_without_a_client_request(self):
        current = [1000.0]
        self.broker.clock = lambda:current[0]
        self.broker.register('pane-a',self.spec)
        operation = self.broker.operations['pane-a','deploy']
        current[0] += 901
        self.broker.start()
        deadline = time.monotonic()+3
        while any(operation.value) and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertFalse(any(operation.value))

    def test_authenticated_api_cannot_read_export_override_or_cross_session_call(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0'}))
            stack.enter_context(patch.object(dashboard,'_lookup_run_light',return_value={'tmux_session':'fixture'}))
            alive = stack.enter_context(patch.object(dashboard,'tmux_alive',return_value=True))
            factory = stack.enter_context(patch('http.client.HTTPSConnection'))
            factory.return_value.getresponse.return_value.status = 200
            app = dashboard.create_app(root, token='fixture-auth', ttyd_enabled=False, remote_nodes_enabled=False)
            client = stack.enter_context(TestClient(app, base_url='https://testserver'))
            prefix = '/api/sessions/pane-a/secret-operations'
            headers = {'Authorization':'Bearer fixture-auth'}
            self.assertEqual(client.post(prefix,json=self.spec).status_code,401)
            created = client.post(prefix,json=self.spec,headers=headers)
            self.assertEqual(created.status_code,200,created.text)
            self.assertNotIn(self.key,created.text)
            self.assertEqual(created.headers['cache-control'],'no-store')
            listing = client.get(prefix,headers=headers)
            self.assertNotIn(self.key,listing.text)
            self.assertEqual(client.get(prefix+'/deploy',headers=headers).status_code,405)
            override = client.post(prefix+'/deploy/call',headers=headers,json={'url':'https://attacker.example.test/'})
            self.assertEqual(override.status_code,400)
            self.assertEqual(client.post('/api/sessions/pane-b/secret-operations/deploy/call',headers=headers).status_code,409)
            factory.assert_not_called()
            response = client.post(prefix+'/deploy/call',headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertNotIn(self.key,response.text)
            self.assertFalse(any(p.is_file() and self.key.encode() in p.read_bytes() for p in root.rglob('*')))
            alive.return_value = False
            self.assertEqual(client.post(prefix+'/deploy/call',headers=headers).status_code,409)
            alive.return_value = True
            self.assertEqual(client.get(prefix,headers=headers).json()['operations'],[])

    @unittest.skipUnless(shutil.which('openssl'), 'OpenSSL required for isolated HTTPS fixture')
    def test_real_https_service_receives_auth_but_echoes_never_reach_agent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate, private = root/'certificate.pem', root/'private.pem'
            config = root/'cert.cnf'
            config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=localhost\n[ext]\nsubjectAltName=IP:127.0.0.1\n')
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                            '-config',str(config),'-keyout',str(private),'-out',str(certificate)],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20)
            received=[]
            key=self.key
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    received.append((self.path,self.headers.get('Authorization')))
                    self.rfile.read(int(self.headers.get('Content-Length','0')))
                    self.send_response(302)
                    self.send_header('Location','https://attacker.example.test/'+key)
                    self.send_header('X-Echo-Secret',key)
                    self.end_headers()
                    self.wfile.write(key.encode())
                def log_message(self, *_):
                    pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(certificate,private)
            server.socket=tls.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                self.broker.register('pane-a',{**self.spec,'url':f'https://127.0.0.1:{server.server_port}/deploy'})
                # Real default certificate verification refuses the fixture.
                with self.assertRaises(ValueError) as error:
                    self.broker.call('pane-a','deploy')
                self.assertNotIn(key,str(error.exception))
                self.assertEqual(received,[])
                trusted=ssl.create_default_context(cafile=str(certificate))
                with patch('ssl.create_default_context',return_value=trusted):
                    result=self.broker.call('pane-a','deploy')
                self.assertEqual(result['http_status'],302)
                self.assertNotIn(key,json.dumps(result))
                self.assertEqual(received,[('/deploy','Bearer '+key)])
            finally:
                server.shutdown();server.server_close();thread.join(3)

    def test_cli_exposes_names_only_without_accepting_key_or_request_overrides(self):
        args = argparse.Namespace(run_id='', dashboard_url='', secret_action='call',name='deploy')
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"http_status":200,"unexpected":"fixture-broker-private-123456"}'
        with patch.dict(os.environ, {'ORCH_RUN_ID':'pane-a'}), \
                patch.object(cli,'_dashboard_api_base',return_value='https://127.0.0.1:7860'), \
                patch.object(cli,'dashboard_token',return_value='fixture-dashboard-auth'), \
                patch.object(cli,'build_opener') as build, \
                patch('sys.stdout',new_callable=io.StringIO) as output:
            build.return_value.open.return_value = response
            cli.cmd_secret(args)
            request = build.return_value.open.call_args.args[0]
            self.assertTrue(request.full_url.endswith('/api/sessions/pane-a/secret-operations/deploy/call'))
            self.assertEqual(request.method,'POST')
            self.assertIsNone(request.data)
            self.assertEqual(build.call_args.args[0].proxies,{})
            self.assertNotIn(self.key,output.getvalue())
        with patch.object(cli,'_dashboard_api_base',return_value='https://untrusted.example.test'):
            args.run_id='pane-a'
            with self.assertRaisesRegex(SystemExit,'loopback'):
                cli.cmd_secret(args)
