from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import terminal_files as files, dashboard


class TerminalFilesTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()

    @unittest.skipUnless(shutil.which('node'), 'Node.js required')
    def test_browser_output_context_ownership(self):
        result=subprocess.run(['node','tests/terminal_file_context.cjs'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_context_preserves_host_and_directory_after_ssh_exit(self):
        remote = files.context(self.root, {'host':'dev', 'cwd':'', 'source':'ssh-process'},
                               {'mode':'auto', 'cwd':'/home/demo/project'})
        old_id = remote['current']['id']
        local = files.context(self.root, {'host':'','cwd':'/local/project','source':'tmux'})
        self.assertNotEqual(local['current']['id'], old_id)
        old = files.get_context(self.root, old_id)
        self.assertEqual(files.resolve_path('reports/a.md:10', old), '/home/demo/project/reports/a.md')
        self.assertEqual(old['host'], 'dev')
        self.assertEqual(files.resolve_path('reports/a.md', local['current']), '/local/project/reports/a.md')
        other = files.context(self.root, {'host':'other','cwd':'','source':'ssh-process'})
        with self.assertRaises(ValueError):
            files.resolve_path('report.md', other['current'])

    def test_copy_mode_does_not_change_context_or_observe_historical_text(self):
        live=files.context(self.root,{'host':'dev','cwd':'','source':'ssh-process','browsing':False})
        history=files.context(self.root,{'host':'dev','cwd':'','source':'ssh-process','browsing':True})
        self.assertEqual(live['current']['id'],history['current']['id'])
        self.assertTrue(live['observing'])
        self.assertFalse(history['observing'])

    def test_unresolved_ssh_never_falls_back_to_local(self):
        state = files.context(self.root, {'host':'','cwd':'','source':'ssh-process','unresolved':True})
        with self.assertRaises(ValueError):
            files.get_context(self.root,state['current']['id'])

    def test_ssh_parse_uses_alias_and_rejects_unreproducible_options(self):
        self.assertEqual(files.ssh_destination('ssh -tt user@dev'), 'user@dev')
        self.assertEqual(files.ssh_destination('ssh -l demo dev'), 'demo@dev')
        self.assertEqual(files.ssh_destination('ssh -p 2222 user@dev'), '')
        self.assertEqual(files.ssh_destination('ssh -o ProxyCommand=bad dev'), '')
        self.assertEqual(files.ssh_destination('echo ssh dev'), '')

    def test_detects_foreground_ssh_but_not_background_git_transport(self):
        def result(text):return subprocess.CompletedProcess([],0,text,'')
        with patch.object(files.subprocess,'run',side_effect=[result('10\t/local\tssh\n'),result('10 1 zsh\n20 10 ssh user@dev\n')]):
            self.assertEqual(files.detect_environment('fixture')['host'],'user@dev')
        with patch.object(files.subprocess,'run',return_value=result('10\t/local\tclaude\n')) as run:
            self.assertEqual(files.detect_environment('fixture')['cwd'],'/local')
            self.assertEqual(run.call_count,1)

    def test_candidate_extraction_and_path_validation(self):
        text='报告：/tmp/test.md 和 reports/figure.png:12 https://example.test/a.md'
        self.assertEqual(files.extract_paths(text),['/tmp/test.md','reports/figure.png:12'])
        for raw in ['//host/a.md','https://example.test/a.md','bad\nfile.md']:
            with self.assertRaises(ValueError):files.resolve_path(raw,{'cwd':'/tmp'})

    def test_home_path_uses_local_home_instead_of_base_directory(self):
        raw = '~/Documents/OSS/project/eli5-hidden-state.html'
        self.assertEqual(files.extract_paths(raw), [raw])
        with patch.dict(os.environ, {'HOME': str(self.root)}):
            for ctx in ({'host': '', 'cwd': '/another/project'}, {'host': '', 'cwd': ''}):
                self.assertEqual(files.resolve_path(raw + ':12:3', ctx),
                                 str(self.root / 'Documents/OSS/project/eli5-hidden-state.html'))

    def test_remote_home_is_never_expanded_using_local_account(self):
        for raw in ('~/report.md', '~someone/report.md'):
            for cwd in ('', '/remote/project'):
                with self.assertRaisesRegex(ValueError, 'absolute remote path'):
                    files.resolve_path(raw, {'host': 'dev', 'cwd': cwd})

    def test_local_home_file_discovery_click_and_html_preview(self):
        client, headers = self.client()
        report = self.root / 'Documents/OSS/project/eli5-hidden-state.html'
        report.parent.mkdir(parents=True)
        report.write_text('<html><body>fixture</body></html>')
        self.stack.enter_context(patch.dict(os.environ, {'HOME': str(self.root)}))
        self.stack.enter_context(patch.object(dashboard, 'tmux_alive', return_value=True))
        self.stack.enter_context(patch.object(dashboard, 'tmux_get_cwd', return_value='/unrelated'))
        self.stack.enter_context(patch.object(files, 'detect_environment',
                                            return_value={'host': '', 'cwd': '/unrelated', 'source': 'tmux'}))
        prefix = '/api/sessions/tmux%3A%3Afixture/'
        ctx = client.get(prefix + 'file-context', headers=headers).json()['current']['id']
        raw = '~/Documents/OSS/project/eli5-hidden-state.html'
        for automatic in (True, False):
            response = client.post(prefix + 'discover-files', headers=headers,
                                   json={'context_id': ctx, 'text': raw, 'automatic': automatic})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['errors'], [])
            self.assertEqual(response.json()['files'][0]['source_path'], str(report))
        response = client.post(prefix + 'terminal-file', headers=headers,
                               json={'context_id': ctx, 'path': raw + '#L12'})
        self.assertEqual(response.status_code, 200, response.text)
        preview = client.get(prefix + 'folders/file', headers=headers,
                             params={'folder': str(report), 'rel': ''})
        self.assertEqual(preview.json()['kind'], 'html')

    def test_model_cannot_use_tools_or_invent_path(self):
        output={'structured_output':{'paths':['reports/test.md','/secret/token','reports/test.md']}}
        with patch.object(files,'resolve_agent_cli',return_value='/fixture/claude'), patch.object(files.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(output),'')) as run:
            self.assertEqual(files.model_paths('报告已生成 reports/\n test.md'),['reports/test.md'])
            argv=run.call_args.args[0]
            self.assertEqual(argv[argv.index('--tools')+1],'')
            self.assertIn('--strict-mcp-config',argv)
            self.assertIn('--disable-slash-commands',argv)
            self.assertIn('"disableAllHooks":true',argv[argv.index('--settings')+1])
            self.assertEqual(run.call_args.kwargs['input'],'报告已生成 reports/\n test.md')

    def client(self):
        self.stack.enter_context(patch.dict(os.environ,{'ORCH_DASHBOARD_CONFIG':str(self.root/'missing.json'),'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0'}))
        app=dashboard.create_app(self.root,token='test-token',ttyd_enabled=False,remote_nodes_enabled=False)
        client=TestClient(app)
        self.addCleanup(client.close)
        self.stack.enter_context(patch.object(dashboard,'_is_allowed_linked_folder',return_value=True))
        return client,{'Authorization':'Bearer test-token'}

    def test_plain_tmux_session_can_discover_and_preview_files(self):
        client,headers=self.client()
        report=self.root/'report.md';report.write_text('# fixture')
        self.stack.enter_context(patch.object(dashboard,'tmux_alive',return_value=True))
        self.stack.enter_context(patch.object(dashboard,'tmux_get_cwd',return_value=str(self.root)))
        self.stack.enter_context(patch.object(files,'detect_environment',return_value={'host':'','cwd':str(self.root),'source':'tmux'}))
        prefix='/api/sessions/tmux%3A%3Afixture/'
        self.assertEqual(client.get(prefix+'file-context').status_code,401)
        response=client.get(prefix+'file-context',headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        ctx=response.json()['current']['id']
        response=client.post(prefix+'discover-files',headers=headers,json={'context_id':ctx,'text':'report.md','automatic':True})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(response.json()['files']),1,response.text)
        listing=client.get(prefix+'folders',headers=headers).json()
        self.assertEqual(listing['folders'][0]['path'],str(report))
        preview=client.get(prefix+'folders/file',headers=headers,params={'folder':str(report),'rel':''})
        self.assertEqual(preview.json()['kind'],'markdown')
        response=client.post(prefix+'discover-files',headers=headers,json={'context_id':ctx,'text':'report.md','automatic':True,'intelligent':True})
        self.assertEqual(response.status_code,400)

    def test_remote_relative_file_uses_historical_context_not_current_host(self):
        client,headers=self.client()
        run={'run_dir':str(self.root),'kind':'run','tmux_session':'fixture'}
        (self.root/'session.json').write_text('{}')
        self.stack.enter_context(patch.object(dashboard,'_lookup_run_light',return_value=run))
        detect=self.stack.enter_context(patch.object(files,'detect_environment',return_value={'host':'dev','cwd':'','source':'ssh-process'}))
        prefix='/api/sessions/fixture/'
        config=client.put(prefix+'file-context',headers=headers,json={'mode':'auto','cwd':'/remote/work'})
        ctx=config.json()['current']['id']
        detect.return_value={'host':'','cwd':'/local/work','source':'tmux'}
        client.get(prefix+'file-context',headers=headers)
        cached=self.root/'cached.md';cached.write_text('remote report')
        with patch.object(dashboard,'fetch_ssh_preview',return_value=cached) as fetch:
            response=client.post(prefix+'terminal-file',headers=headers,json={'context_id':ctx,'path':'reports/test.md'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(fetch.call_args.args[:2],('dev','/remote/work/reports/test.md'))
