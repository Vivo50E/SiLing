from contextlib import ExitStack
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, proxy_mode


class ProxyModeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.run = self.root / 'fixture'
        self.run.mkdir()
        self.meta = self.run / 'session.json'
        self.original = {'name':'agent', 'agent':'claude', 'cwd':str(self.root),
                         'resume_id':'exact-native', 'model':'keep-model', 'label':'Keep name'}
        self.meta.write_text(json.dumps(self.original))
        self.stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0',
            'ORCH_DASHBOARD_CONFIG':str(self.root/'none')}))
        self.send = self.stack.enter_context(patch.object(dashboard, 'tmux_send'))
        self.stop = self.stack.enter_context(patch.object(dashboard, '_graceful_stop_agent'))
        self.client = TestClient(dashboard.create_app(self.root, token='fixture', ttyd_enabled=False, remote_nodes_enabled=False))
        self.addCleanup(self.client.close)
        self.headers = {'Authorization':'Bearer fixture'}
        self.url = '/api/sessions/fixture::agent/proxy-mode'

    def save(self, body):
        return self.client.post(self.url, json=body, headers=self.headers)

    def test_save_is_pending_and_preserves_process_identity(self):
        for mode in proxy_mode.MODES:
            result = self.save({'mode':mode})
            self.assertEqual(result.status_code, 200, result.text)
            saved = json.loads(self.meta.read_text())
            self.assertEqual(saved, dict(self.original, proxy_mode=mode))
            row = dashboard._lookup_run_light(self.root, 'fixture::agent')
            self.assertEqual(row['proxy_mode'], mode)
            self.assertEqual(row['proxy_mode_applied'], '')
            snapshot = dashboard._snapshot_entry_from_run(row, 0, 0)
            self.assertEqual(snapshot['proxy_mode'], mode)
        self.send.assert_not_called()
        self.stop.assert_not_called()

    def test_validation_and_auth_leave_metadata_unchanged(self):
        before = self.meta.read_bytes()
        for body in [[], {}, {'mode':None}, {'mode':[]}, {'mode':'devin; echo unsafe'}]:
            self.assertEqual(self.save(body).status_code, 400)
        self.client.cookies.clear()
        self.assertEqual(self.client.post(self.url, json={'mode':'devin'}).status_code, 401)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.meta.read_bytes(), before)
        self.meta.write_text(json.dumps(dict(self.original, agent='terminal')))
        self.assertEqual(self.save({'mode':'devin'}).status_code, 409)

    def test_task_only_changes_selected_record(self):
        self.meta.unlink()
        state = self.run / 'state.json'
        state.write_text(json.dumps({'agent':self.original, 'other':{'agent':'codex'}}))
        self.assertEqual(self.save({'mode':'devin'}).status_code, 200)
        saved = json.loads(state.read_text())
        self.assertEqual(saved['agent']['proxy_mode'], 'devin')
        self.assertEqual(saved['other'], {'agent':'codex'})

    def test_provider_probe_is_local_and_policy_blocks_silent_fallback(self):
        with patch.object(proxy_mode, 'devin_skill', return_value=None), patch.object(proxy_mode, 'cmux_cli', return_value=''):
            data = self.client.get(self.url, headers=self.headers).json()
            self.assertEqual(data['available'], {'devin':False, 'cmux-cloud':False})
            self.assertIn('not found at launch', proxy_mode.instructions('devin'))
        with patch.object(proxy_mode, 'devin_skill', return_value=self.root/'skill with spaces/SKILL.md'):
            self.assertIn(str(self.root/'skill with spaces/SKILL.md'), proxy_mode.instructions('devin'))
        for mode in ('devin', 'cmux-cloud'):
            prompt = proxy_mode.instructions(mode)
            self.assertIn('never silently fall back', prompt)
            self.assertIn('do not replay old tasks', prompt)
        self.assertIn('OFF', proxy_mode.instructions('local'))

    def test_resume_passes_saved_policy_and_native_identity_to_launcher(self):
        self.save({'mode':'devin'})
        calls = []
        def launch(args, **kwargs):
            if '--run-name' not in args:
                return subprocess.CompletedProcess(args, 0, '', '')
            calls.append(args)
            folder = self.root / args[args.index('--run-name')+1]
            folder.mkdir(exist_ok=True)
            (folder/'session.json').write_text('{}')
            return subprocess.CompletedProcess(args, 0, f'Session: fixture-child\nOutput: {folder}\n', '')
        with patch.object(dashboard, '_native_resume_check', return_value={'status':'ready'}), patch.object(dashboard, '_schedule_native_resume_capture'), patch.object(dashboard, '_run_with_recovery_model', side_effect=lambda row:row), patch.object(dashboard.subprocess, 'run', side_effect=launch):
            result = self.client.post('/api/resume', headers=self.headers, json={'run_id':'fixture::agent'})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(calls[0][calls[0].index('--proxy-mode')+1], 'devin')
        self.assertEqual(calls[0][calls[0].index('--resume-id')+1], 'exact-native')
        self.assertEqual(calls[0][calls[0].index('--model')+1], 'keep-model')


class ProxyLauncherTests(unittest.TestCase):
    def test_native_cli_receives_one_quoted_policy_on_new_resume_and_fork(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root/'scripts'; scripts.mkdir()
            package = root/'agent_orchestrator'; package.mkdir()
            for name in ('run.sh', 'cursor-sync-output.cjs', 'cursor-model-state.cjs'):
                shutil.copy(repo/'scripts'/name, scripts/name)
            for name in ('agent_cli.py', 'proxy_mode.py'):
                shutil.copy(repo/'agent_orchestrator'/name, package/name)
            (scripts/'watcher.sh').write_text('#!/bin/sh\nexit 0\n')
            bin_dir = root/'bin'; bin_dir.mkdir()
            (bin_dir/'python3').symlink_to(sys.executable)
            capture = root/'argv.json'
            cli = f'#!{sys.executable}\nimport json, pathlib, sys\npathlib.Path({str(capture)!r}).write_text(json.dumps(sys.argv[1:]))\n'
            for name in ('claude','codex','agent'):
                (bin_dir/name).write_text(cli); (bin_dir/name).chmod(0o700)
            (bin_dir/'tmux').write_text(f'#!{sys.executable}\nimport subprocess,sys\nif sys.argv[1] == "new-session": subprocess.run(["bash", "-c", sys.argv[-1]], stdin=subprocess.DEVNULL, check=False)\n')
            (bin_dir/'tmux').chmod(0o700)
            env = dict(os.environ, PATH=f'{bin_dir}:/usr/bin:/bin', ORCH_OUTPUTS_DIR=str(root/'outputs'), HOME=str(root))
            for agent in ('claude','codex','cursor'):
                for launch in ('new','resume','fork'):
                    if agent == 'cursor' and launch == 'fork':
                        continue
                    for mode in ('devin','cmux-cloud','local'):
                        with self.subTest(agent=agent, launch=launch, mode=mode):
                            name = f'{agent}-{launch}-{mode}'
                            args = ['bash', str(scripts/'run.sh'), '--no-attach', '--run-name', name, '--proxy-mode', mode]
                            if launch != 'new': args += ['--resume-id' if launch == 'resume' else '--fork-id', 'native-original']
                            args += [agent, 'fixture', str(root)]
                            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            argv = json.loads(capture.read_text())
                            self.assertTrue(argv[-1].startswith('[SiLing pane execution preference]'))
                            self.assertIn('OFF' if mode == 'local' else f'Remote proxy mode: {mode}', argv[-1])
                            if launch != 'new': self.assertIn('native-original', argv)
                            saved = json.loads((root/'outputs'/name/'session.json').read_text())
                            self.assertEqual(saved['proxy_mode_applied'], mode)
