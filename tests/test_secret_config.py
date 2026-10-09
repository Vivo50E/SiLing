from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, secret_config
from agent_orchestrator.remote_nodes import RemoteNodeRegistry, RemoteNodeSettings, qualify_run_id
from urllib.parse import quote


class SecretConfigurationTests(unittest.TestCase):
    def spec(self, location, **changes):
        return {'directory':str(Path(location).resolve()), 'host':'', 'name':'SLACK_BOT_TOKEN',
                'value':'fixture-not-a-real-secret', 'confirm':True, **changes}

    def test_literal_atomic_update_permissions_preservation_and_no_tmux(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); target=root/'backend.env'
            target.write_text('# keep\nOTHER="original"\nSLACK_BOT_TOKEN=old\nSLACK_BOT_TOKEN=duplicate\n')
            with patch.object(secret_config.subprocess, 'run') as run:
                secret_config.write(self.spec(root,value='fixture "quoted" \\ 中文'))
                run.assert_not_called()
            self.assertEqual(target.read_text(), '# keep\nOTHER="original"\nSLACK_BOT_TOKEN="fixture \\"quoted\\" \\\\ 中文"\n')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
            self.assertEqual(sorted(p.name for p in root.iterdir()),['backend.env'])
            secret_config.write(self.spec(root,name='NEW_KEY',value='fixture-new'))
            self.assertTrue(target.read_text().endswith('NEW_KEY="fixture-new"\n'))

    def test_rejects_invalid_values_fields_symlinks_links_and_unsafe_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); target=root/'backend.env'; target.write_text('KEEP=original\n')
            for changes in ({'confirm':False},{'name':'BAD\nNAME'},{'value':'fixture\nattack'},
                            {'value':'${COMMAND}'},{'value':'`command`'},{'value':''},{'host':'-oProxyCommand=attack'},
                            {'directory':str(root)+'/../other'},{'value':'x'*4097},{'value':123},{'extra':'field'}):
                with self.assertRaises(ValueError): secret_config.write(self.spec(root,**changes))
                self.assertEqual(target.read_text(),'KEEP=original\n')
            target.unlink(); outside=root/'outside'; outside.write_text('KEEP=outside\n'); target.symlink_to(outside)
            with self.assertRaises(OSError):secret_config.write(self.spec(root))
            self.assertEqual(outside.read_text(),'KEEP=outside\n'); target.unlink()
            os.link(outside,target)
            with self.assertRaises(ValueError):secret_config.write(self.spec(root))
            target.unlink(); target.mkdir()
            with self.assertRaises(ValueError):secret_config.write(self.spec(root))
            target.rmdir(); os.chmod(root,0o777)
            try:
                with self.assertRaises(ValueError):secret_config.write(self.spec(root))
            finally:os.chmod(root,0o700)
            link=root/'linked'; link.symlink_to(root,target_is_directory=True)
            with self.assertRaises(OSError):secret_config.write({**self.spec(root),'directory':str(link)})

    @unittest.skipUnless(shutil.which('git'),'Git required')
    def test_git_ignored_only_and_staging_is_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            subprocess.run(['git','init','-q',str(root)],check=True)
            with self.assertRaises(ValueError):secret_config.write(self.spec(root))
            (root/'.gitignore').write_text('backend.env\n')
            original_replace=secret_config.os.replace
            def replace(source,destination,**kwargs):
                self.assertNotIn(root,Path(source).resolve().parents)
                self.assertEqual(stat.S_IMODE(Path(source).stat().st_mode),0o600)
                return original_replace(source,destination,**kwargs)
            with patch.object(secret_config.os,'replace',side_effect=replace):secret_config.write(self.spec(root))
            subprocess.run(['git','-C',str(root),'add','-f','backend.env'],check=True)
            with self.assertRaises(ValueError):secret_config.write(self.spec(root))

    def test_failed_atomic_replace_cleans_staging_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); target=root/'backend.env';target.write_text('KEEP=original\n')
            staging=[]; original=secret_config.tempfile.mkstemp
            def create(**kwargs):
                fd,path=original(**kwargs);staging.append(Path(path));return fd,path
            with patch.object(secret_config.tempfile,'mkstemp',side_effect=create), \
                    patch.object(secret_config.os,'replace',side_effect=OSError('fixture-not-a-real-secret')):
                with self.assertRaises(OSError):secret_config.write(self.spec(root))
            self.assertEqual(target.read_text(),'KEEP=original\n')
            self.assertTrue(staging);self.assertTrue(all(not p.exists() for p in staging))

    def test_multiline_file_is_rejected_without_damage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();target=root/'backend.env'; original='OTHER="first\nsecond"\n';target.write_text(original)
            with self.assertRaises(ValueError):secret_config.write(self.spec(root))
            self.assertEqual(target.read_text(),original)

    def test_ssh_uses_fixed_isolated_helper_and_stdin_only_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            spec=self.spec(directory,host='fixture-box')
            with patch.object(secret_config.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
                secret_config.write(spec)
            argv=run.call_args.args[0];kwargs=run.call_args.kwargs
            self.assertNotIn(spec['value'],repr(argv));self.assertNotIn(spec['directory'],repr(argv))
            self.assertIn('StrictHostKeyChecking=yes',argv);self.assertIn('BatchMode=yes',argv)
            self.assertIn('ForwardAgent=no',argv);self.assertIn('PermitLocalCommand=no',argv)
            self.assertIn('python3 -I -c ',argv[-1])
            self.assertEqual(json.loads(kwargs['input']),{**spec,'host':''})
            self.assertEqual(kwargs['stdout'],subprocess.DEVNULL);self.assertEqual(kwargs['stderr'],subprocess.DEVNULL)
            run.assert_called_once()
            # Execute exactly the shipped helper in a fresh isolated process.
            result=subprocess.run([sys.executable,'-I','-c',Path(secret_config.__file__).read_text()],
                                  input=kwargs['input'],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,b'')
            self.assertIn(spec['value'],(Path(directory)/'backend.env').read_text())
            with patch.object(secret_config.subprocess,'run',side_effect=subprocess.TimeoutExpired(['ssh'],20)) as run:
                with self.assertRaises(subprocess.TimeoutExpired):secret_config.write(spec)
                run.assert_called_once()

    def test_api_auth_transport_generic_errors_and_no_terminal_input(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root=Path(directory).resolve();outputs=root/'outputs';outputs.mkdir()
            stack.enter_context(patch.object(dashboard,'_lookup_run_light',return_value={'agent':'claude','tmux_session':'fixture'}))
            terminal=stack.enter_context(patch.object(dashboard,'_tmux_target_pane'))
            app=dashboard.create_app(outputs,token='fixture-auth',ttyd_enabled=False,remote_nodes_enabled=False)
            client=stack.enter_context(TestClient(app,base_url='https://testserver'))
            url='/api/sessions/fixture/secret-config';headers={'Authorization':'Bearer fixture-auth'}
            spec=self.spec(root)
            self.assertEqual(client.post(url,json=spec).status_code,401)
            with patch.object(secret_config,'write') as write:
                blocked=client.post(url,json=spec,headers={**headers,'Origin':'https://evil.invalid'})
                self.assertEqual(blocked.status_code,403);write.assert_not_called()
            response=client.post(url,json=spec,headers={**headers,'Origin':'https://testserver'})
            self.assertEqual(response.json(),{'ok':True});self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertNotIn(spec['value'],response.text);terminal.assert_not_called()
            for data in ([spec],{**spec,'value':'fixture\nattack'},{**spec,'value':42}):
                response=client.post(url,json=data,headers=headers)
                self.assertEqual(response.status_code,400);self.assertEqual(response.json(),{'detail':secret_config.FAILURE})
            with patch.object(secret_config,'write',side_effect=OSError(spec['value'])):
                response=client.post(url,json=spec,headers=headers)
                self.assertNotIn(spec['value'],response.text)
            self.assertEqual(client.post(url,content=b'x'*16385,headers=headers).status_code,413)
            insecure=stack.enter_context(TestClient(app,base_url='http://testserver'))
            self.assertEqual(insecure.post(url,json=spec,headers=headers).status_code,403)

    def test_remote_proxy_uses_protected_transport_and_never_reflects_node_echoes(self):
        for destination,allowed in [('http://192.0.2.1:7860',False),('https://node.invalid',True)]:
            with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                node=RemoteNodeSettings(id='fixture-node',label='Fixture',url=destination,token='fixture-node-auth')
                registry=RemoteNodeRegistry([node]);stack.enter_context(patch.object(dashboard,'RemoteNodeRegistry',return_value=registry))
                stack.enter_context(patch.object(registry,'start'));stack.enter_context(patch.object(registry,'stop'))
                app=dashboard.create_app(Path(directory),token='fixture-auth',ttyd_enabled=False)
                client=stack.enter_context(TestClient(app,base_url='https://testserver'))
                spec=self.spec(directory)
                response=httpx.Response(400,json={'detail':spec['value']},headers={'X-Echo':spec['value']})
                upstream=stack.enter_context(patch.object(httpx.AsyncClient,'request',new_callable=AsyncMock,return_value=response))
                run_id=quote(qualify_run_id('fixture-node','fixture'),safe='')
                result=client.post('/api/sessions/'+run_id+'/secret-config',json=spec,headers={'Authorization':'Bearer fixture-auth'})
                self.assertNotIn(spec['value'],result.text);self.assertNotIn('x-echo',result.headers)
                if allowed:
                    self.assertEqual(result.status_code,502);upstream.assert_awaited_once()
                    self.assertEqual(upstream.call_args.kwargs['headers']['Authorization'],'Bearer fixture-node-auth')
                    self.assertEqual(upstream.call_args.kwargs['params'],{})
                    for body,code in [({'ok':True},200),({'ok':True,'echo':spec['value']},502)]:
                        upstream.reset_mock();upstream.return_value=httpx.Response(200,json=body,headers={'X-Echo':spec['value']})
                        result=client.post('/api/sessions/'+run_id+'/secret-config',json=spec,headers={'Authorization':'Bearer fixture-auth','Origin':'https://testserver'})
                        self.assertEqual(result.status_code,code)
                        self.assertNotIn(spec['value'],result.text);self.assertNotIn('x-echo',result.headers)
                        self.assertNotIn('origin',upstream.call_args.kwargs['headers'])
                        upstream.assert_awaited_once()
                else:
                    self.assertEqual(result.status_code,403);upstream.assert_not_awaited()
