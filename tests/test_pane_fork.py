"""Forking never resumes/stops the original conversation or duplicates a retry."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard
from agent_orchestrator.pane_groups import PaneGroups


class PaneForkTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source = {'run_id': 'source::agent', 'agent': 'claude', 'alive': True,
                       'cwd': str(self.root), 'display_name': 'Example', 'model': 'fixture-model',
                       'resume_id': 'source-native-id', 'terminal_theme': 'soft-green', 'effort': 'high'}
        self.calls = []
        self.stack.enter_context(patch.object(dashboard, '_lookup_run', side_effect=lambda *args: dict(self.source)))
        self.stack.enter_context(patch.object(dashboard, '_run_with_native_model_effort', side_effect=lambda row: row))
        self.stack.enter_context(patch.object(dashboard, '_schedule_native_resume_capture'))
        self.stack.enter_context(patch.object(dashboard, 'resolve_agent_cli', return_value='/fake/agent'))
        self.stack.enter_context(patch.object(dashboard.subprocess, 'run', side_effect=self.launch))
        self.kill = self.stack.enter_context(patch.object(dashboard, 'tmux_kill'))
        self.send = self.stack.enter_context(patch.object(dashboard, 'tmux_send'))
        self.app = dashboard.create_app(self.root, token='test', ttyd_enabled=False, remote_nodes_enabled=False)
        self.client = self.stack.enter_context(TestClient(self.app))
        self.body = {'kind': 'conversation', 'request_id': 'request-1'}
        self.help_text = 'fork --fork-session'
        self.fail_launch = False

    def launch(self, args, **kwargs):
        if '--help' in args:
            return subprocess.CompletedProcess(args, 0, self.help_text, '')
        if '--run-name' not in args:
            return subprocess.CompletedProcess(args, 0, '', '')
        self.calls.append(args)
        if self.fail_launch:
            raise subprocess.TimeoutExpired(args, 1)
        folder = self.root / args[args.index('--run-name') + 1]
        folder.mkdir(exist_ok=True)
        (folder / 'session.json').write_text('{}')
        return subprocess.CompletedProcess(args, 0, f'Session: child\nOutput: {folder}\n', '')

    def post(self, **values):
        return self.client.post('/api/sessions/source::agent/fork', headers={'Authorization':'Bearer test'},
                                json={**self.body, **values})

    def test_claude_fork_has_new_identity_keeps_source_and_retries_once(self):
        groups = PaneGroups(self.root)
        groups.change({'action':'create', 'name':'Project', 'color':'blue'})
        gid = groups.view([])['groups'][0]['id']
        groups.change({'action':'assign', 'group_id':gid}, [self.source])
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        args = self.calls[0]
        self.assertEqual(args[args.index('--fork-id')+1], 'source-native-id')
        self.assertNotIn('--resume-id', args)
        new_id = args[args.index('--native-session-id')+1]
        self.assertNotEqual(new_id, self.source['resume_id'])
        self.assertEqual(result['group_id'], gid)
        self.assertEqual(self.post().json()['run_id'], result['run_id'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.post(kind='configuration').status_code, 409)
        saved = json.loads((Path(result['run_dir'])/'session.json').read_text())
        self.assertEqual(saved['forked_from_run_id'], self.source['run_id'])
        self.kill.assert_not_called()
        self.send.assert_not_called()

    def test_codex_fork_does_not_save_parent_as_child_resume_id(self):
        self.source['agent'] = 'codex'
        result = self.post()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn('--fork-id', self.calls[0])
        self.assertNotIn('--resume-id', self.calls[0])
        self.assertNotIn('--native-session-id', self.calls[0])
        self.assertNotIn('preallocated_resume_id', result.json())

    def test_missing_identity_unsupported_agent_and_old_cli_fail_before_spawn(self):
        self.source['resume_id'] = ''
        self.assertEqual(self.post().status_code, 409)
        self.source['resume_id'] = 'source-native-id'
        self.help_text = 'resume only'
        self.assertEqual(self.post().status_code, 409)
        self.source['agent'] = 'cursor'
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(self.calls)

    def test_terminal_configuration_is_fresh_shell_and_auth_is_required(self):
        self.source['agent'] = 'terminal'
        self.assertEqual(self.client.post('/api/sessions/source/fork', json=self.body).status_code, 401)
        response = self.post(kind='configuration')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('--fork-id', self.calls[0])
        self.assertNotIn('--resume-id', self.calls[0])
        self.assertNotIn('--model', self.calls[0])
        self.assertEqual(self.calls[0][-1], str(self.root))

    def test_uncertain_launch_cannot_be_repeated(self):
        self.fail_launch = True
        self.assertEqual(self.post().status_code, 500)
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(len(self.calls), 1)

    def test_pending_fork_never_discovers_parent_from_inherited_output(self):
        row = {'agent':'codex', 'forked_from_resume_id':'parent', 'cwd':str(self.root)}
        with patch.object(dashboard, '_extract_resume_from_text') as extract, patch.object(dashboard, '_find_codex_resume') as find:
            self.assertEqual(dashboard._discover_resume_metadata(row, 'codex resume parent'), {})
            extract.assert_not_called()
            find.assert_not_called()

    def test_remote_fork_routes_to_owner_and_qualifies_both_identities(self):
        import os
        import httpx
        from unittest.mock import AsyncMock
        from agent_orchestrator.remote_nodes import qualify_run_id
        config = self.root/'dashboard.local.json'
        config.write_text(json.dumps({'remote_nodes':[{'id':'dev', 'url':'http://127.0.0.1:17861', 'token':'remote-token'}]}))
        with patch.dict(os.environ, {'ORCH_DASHBOARD_CONFIG':str(config)}):
            app = dashboard.create_app(self.root, token='test', ttyd_enabled=False)
        remote_id = qualify_run_id('dev', self.source['run_id'])
        response = httpx.Response(200, json={'ok':True, 'run_id':'child::fork', 'forked_from':self.source['run_id']})
        with patch.object(httpx.AsyncClient, 'request', new=AsyncMock(return_value=response)) as proxy, TestClient(app) as client:
            result = client.post(f'/api/sessions/{remote_id}/fork', headers={'Authorization':'Bearer test'}, json=self.body)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['run_id'], qualify_run_id('dev', 'child::fork'))
            self.assertEqual(result.json()['forked_from'], remote_id)
            fork_calls = [call for call in proxy.call_args_list if call.args[1].endswith('/fork')]
            self.assertEqual(len(fork_calls), 1)
            self.assertTrue(fork_calls[0].args[1].endswith('/api/sessions/source%3A%3Aagent/fork'))
            self.assertEqual(fork_calls[0].kwargs['headers']['Authorization'], 'Bearer remote-token')
            self.assertEqual(json.loads(fork_calls[0].kwargs['content']), self.body)
        self.assertFalse(self.calls)

    def test_codex_capture_requires_parent_lineage_and_rejects_ambiguity(self):
        folder = self.root/'.codex/sessions/2026/10/10'
        folder.mkdir(parents=True)
        def write(name, parent):
            (folder/f'rollout-{name}.jsonl').write_text(json.dumps({'type':'session_meta', 'payload':{
                'id':name, 'forked_from_id':parent, 'cwd':str(self.root), 'timestamp':'2026-10-10T12:00:01Z'}})+'\n')
        write('unrelated', None)
        write('child', 'parent')
        with patch.object(dashboard.Path, 'home', return_value=self.root):
            meta, candidates = dashboard._find_codex_resume_near_start(str(self.root), '2026-10-10T12:00:00Z', fork_parent_id='parent')
            self.assertEqual(meta['resume_id'], 'child')
            write('second-child', 'parent')
            meta, candidates = dashboard._find_codex_resume_near_start(str(self.root), '2026-10-10T12:00:00Z', fork_parent_id='parent')
            self.assertEqual(meta, {})
            self.assertEqual(len(candidates), 2)


class ForkLauncherTests(unittest.TestCase):
    def test_native_commands_and_metadata_use_independent_identity(self):
        import os
        import shlex
        import shutil
        import sys
        repo = Path(__file__).resolve().parents[1]
        for agent in ('claude', 'codex'):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root/'scripts').mkdir()
                (root/'agent_orchestrator').mkdir()
                shutil.copy(repo/'scripts/run.sh', root/'scripts/run.sh')
                shutil.copy(repo/'agent_orchestrator/agent_cli.py', root/'agent_orchestrator/agent_cli.py')
                binary = root/'bin'
                binary.mkdir()
                log = root/'tmux.json'
                for name, script in {
                    agent: '#!/bin/sh\nexit 0\n',
                    'nohup': '#!/bin/sh\nexit 0\n',
                    'tmux': f'#!{sys.executable}\nimport json,sys,pathlib\npathlib.Path({str(log)!r}).write_text(json.dumps(sys.argv[1:]))\n',
                }.items():
                    (binary/name).write_text(script)
                    (binary/name).chmod(0o700)
                args = ['bash', str(root/'scripts/run.sh'), '--no-attach', '--fork-id', 'parent-id',
                        '--run-name', 'fork-test', '--model', 'chosen-model', '--effort', 'high']
                if agent == 'claude':
                    args += ['--native-session-id', 'child-id']
                args += [agent, 'child', str(root)]
                env = {'PATH':f'{binary}:{Path(sys.executable).parent}:{os.defpath}',
                       'HOME':str(root), 'ORCH_OUTPUTS_DIR':str(root/'outputs')}
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                command = [part.rstrip(";") for part in shlex.split(json.loads(log.read_text())[-1])]
                self.assertIn('parent-id', command)
                self.assertIn('chosen-model', command)
                meta = json.loads((root/'outputs/fork-test/session.json').read_text())
                self.assertEqual(meta['forked_from_resume_id'], 'parent-id')
                self.assertNotEqual(meta['resume_id'], 'parent-id')
                if agent == 'claude':
                    self.assertIn('--fork-session', command)
                    self.assertEqual(command[command.index('--session-id')+1].rstrip(';'), 'child-id')
                    self.assertEqual(meta['resume_id'], 'child-id')
                else:
                    self.assertIn('fork', command)
                    self.assertNotIn('resume', command)
                    self.assertEqual(meta['resume_id'], '')
