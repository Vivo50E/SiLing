import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent_orchestrator.plugins import Plugins
from agent_orchestrator import speckit_plugin


class PluginTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / 'project with spaces'
        self.project.mkdir()
        self.manager = Plugins(self.root / 'outputs')
        self.body = {'cwd': str(self.project), 'agent': 'codex', 'stage': 'setup', 'request': ''}

    def enable(self):
        self.manager.status(True)

    def launch_body(self):
        prepared = self.manager.prepare(self.body)
        return {**self.body, 'preview_id': prepared['preview_id'], 'idempotency_key': 'fixture'}

    def test_disabled_by_default_and_persistent(self):
        self.assertFalse(self.manager.status()['enabled'])
        with self.assertRaisesRegex(ValueError, 'Enable'):
            self.manager.prepare(self.body)
        self.enable()
        self.assertTrue(Plugins(self.root / 'outputs').status()['enabled'])
        self.manager.status(False)
        with self.assertRaises(ValueError):
            self.manager.launch(self.body, Mock())
        with self.assertRaises(ValueError):
            self.manager.status('false')

    def test_setup_preview_is_read_only_with_missing_cli(self):
        self.enable()
        original = self.project / 'README.md'
        original.write_text('Existing user document')
        before = list(self.project.iterdir())
        with patch('agent_orchestrator.speckit_plugin.shutil.which', return_value=None), patch('agent_orchestrator.speckit_plugin.Path.home', return_value=self.root):
            preview = self.manager.prepare(self.body)
        self.assertIsNone(preview['project']['specify_cli'])
        self.assertEqual(list(self.project.iterdir()), before)
        self.assertEqual(original.read_text(), 'Existing user document')
        self.assertIn('empty staging directory', preview['delegation']['prompt'])
        self.assertFalse(preview['delegation']['inherit_linked_items'])

    def test_detects_current_and_legacy_instructions_and_rejects_missing_stage(self):
        self.enable()
        self.body['stage'] = 'plan'
        with self.assertRaisesRegex(ValueError, 'not installed'):
            self.manager.prepare(self.body)
        for agent, relative in [('codex', '.agents/skills/speckit-plan/SKILL.md'),
                                ('claude', '.claude/commands/speckit.plan.md'),
                                ('cursor', '.cursor/commands/speckit.plan.md')]:
            path = self.project / relative
            path.parent.mkdir(parents=True)
            path.write_text('Plan this feature')
            self.body['agent'] = agent
            prepared = self.manager.prepare(self.body)
            self.assertEqual(prepared['project']['stages']['plan'], relative)
            self.assertIn(relative, prepared['delegation']['prompt'])

    def test_invalid_paths_agents_and_symlink_escape(self):
        for body in [{**self.body, 'cwd': '.'}, {**self.body, 'cwd': str(self.root / 'missing')},
                     {**self.body, 'agent': 'shell'}, {**self.body, 'stage': 'taskstoissues'},
                     {**self.body, 'request': 'a' * 16001}]:
            with self.assertRaises(ValueError):
                speckit_plugin.prepare(body)
        outside = self.root / 'outside'
        outside.mkdir()
        (self.project / '.agents').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            speckit_plugin.prepare(self.body)

    def test_launch_retries_are_idempotent_and_payload_changes_rejected(self):
        self.enable()
        body = self.launch_body()
        spawn = Mock(return_value={'run_id': 'child', 'delegation_prompt_status': 'pending'})
        self.assertFalse(self.manager.launch(body, spawn)['replayed'])
        self.assertTrue(Plugins(self.root / 'outputs').launch(body, spawn)['replayed'])
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0]['cwd'], str(self.project))
        self.assertNotIn('parent_run_id', spawn.call_args.args[0])
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.manager.launch({**body, 'request': 'different'}, spawn)
        self.manager.status(False)
        with self.assertRaisesRegex(ValueError, 'Enable'):
            self.manager.launch(body, spawn)

    def test_uncertain_spawn_never_repeats(self):
        self.enable()
        body = self.launch_body()
        spawn = Mock(side_effect=RuntimeError('connection lost after process creation'))
        with self.assertRaises(RuntimeError):
            self.manager.launch(body, spawn)
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            Plugins(self.root / 'outputs').launch(body, spawn)
        spawn.assert_called_once()

    def test_api_validation_and_disable(self):
        from agent_orchestrator import dashboard
        from fastapi.testclient import TestClient
        with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
            app = dashboard.create_app(self.root / 'api', token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
        client = TestClient(app)
        self.addCleanup(client.close)
        headers = {'Authorization': 'Bearer fixture'}
        base = '/api/plugins/spec-kit/'
        self.assertFalse(client.get('/api/plugins', headers=headers).json()['plugins'][0]['enabled'])
        self.assertEqual(client.post(base+'prepare', headers=headers, json=self.body).status_code, 400)
        for invalid in [[], {'enabled': None}, {'enabled': 'false'}, {}]:
            self.assertEqual(client.post(base+'configure', headers=headers, json=invalid).status_code, 400)
        self.assertEqual(client.post(base+'configure', headers=headers, json={'enabled': True}).status_code, 200)
        self.assertEqual(client.post(base+'prepare', headers=headers, json=self.body).status_code, 200)
        self.assertEqual(client.post(base+'prepare', headers=headers, content='x'*100001).status_code, 413)
        self.assertEqual(client.post(base+'unknown', headers=headers, json={}).status_code, 404)
        client.post(base+'configure', headers=headers, json={'enabled': False})
        self.assertEqual(client.post(base+'launch', headers=headers, json=self.body).status_code, 400)

    def test_api_launch_delivers_prompt_to_one_new_background_session(self):
        import json
        import sys
        from unittest.mock import AsyncMock
        from agent_orchestrator import dashboard
        from fastapi.testclient import TestClient
        scripts = self.root / 'scripts'
        scripts.mkdir()
        launcher = scripts / 'run.sh'
        launcher.write_text(f"#!{sys.executable}\n" + """import json, os, pathlib, sys
args = sys.argv[1:]
name = args[args.index('--run-name') + 1]
folder = pathlib.Path(os.environ['ORCH_OUTPUTS_DIR']) / name
folder.mkdir(parents=True)
(folder / 'session.json').write_text(json.dumps({'name': args[-2], 'agent': args[-3], 'cwd': args[-1], 'tmux_session': 'plugin-fixture'}))
print('Session: plugin-fixture')
print('Output: ' + str(folder))
""")
        launcher.chmod(0o700)
        with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
            app = dashboard.create_app(self.root / 'api-launch', ttyd_enabled=False, remote_nodes_enabled=False)
        with patch.object(dashboard, 'SCRIPTS_DIR', scripts), patch.object(
            dashboard, '_deliver_first_prompt', new=AsyncMock(return_value=True)
        ) as deliver, patch.object(dashboard, '_schedule_native_resume_capture'), patch.object(
            dashboard, '_preallocate_native_resume_meta', return_value=({}, '')
        ):
            client = TestClient(app)
            self.addCleanup(client.close)
            base = '/api/plugins/spec-kit/'
            client.post(base+'configure', json={'enabled': True})
            prepared = client.post(base+'prepare', json=self.body).json()
            body = {**self.body, 'preview_id': prepared['preview_id'], 'idempotency_key': 'api-fixture'}
            first = client.post(base+'launch', json=body)
            self.assertEqual(first.status_code, 200, first.text)
            second = client.post(base+'launch', json=body)
            self.assertEqual(second.json()['run_id'], first.json()['run_id'])
            self.assertTrue(second.json()['replayed'])
            deliver.assert_awaited_once_with('plugin-fixture', prepared['delegation']['prompt'])
            metadata = json.loads((Path(first.json()['run_dir']) / 'session.json').read_text())
            self.assertEqual(metadata['parent_run_id'], '')
            self.assertEqual(metadata['delegation_prompt_status'], 'delivered')
            self.assertEqual(metadata['cwd'], str(self.project))
