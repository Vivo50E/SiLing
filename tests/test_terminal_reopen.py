"""Reopening an ended shell preserves its configuration, not dead processes."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class TerminalReopenTests(unittest.TestCase):
    def test_reopen_without_native_id_preserves_source_and_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_dir = root / 'old'
            source_dir.mkdir()
            (source_dir / 'history.log').write_text('old history\n')
            old_metadata = {'agent': 'terminal', 'label': 'Shell test'}
            (source_dir / 'session.json').write_text(json.dumps(old_metadata))
            source = dict(old_metadata, alive=False, run_id='old::shell',
                          run_dir=str(source_dir), cwd=temp, terminal_theme='soft-green',
                          panel_state='paused', linked_folders=[{'path': temp, 'label': 'Project'}],
                          model='stale-model', resume_id='stale-id')
            calls = []
            def spawn(args, **kwargs):
                if '--run-name' not in args:
                    return subprocess.CompletedProcess(args, 0, '', '')
                calls.append((args, kwargs))
                run_name = args[args.index('--run-name') + 1]
                run_dir = root / run_name
                run_dir.mkdir()
                (run_dir / 'session.json').write_text('{}')
                return subprocess.CompletedProcess(args, 0, f'Session: test-new\nOutput: {run_dir}\n', '')
            with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0):
                app = dashboard.create_app(root, ttyd_enabled=False, remote_nodes_enabled=False)
            with TestClient(app) as client, \
                    patch.object(dashboard, '_lookup_run', return_value=source), \
                    patch.object(dashboard, '_schedule_native_resume_capture'), \
                    patch.object(dashboard, '_run_with_native_model_effort', side_effect=AssertionError('not an agent')), \
                    patch.object(dashboard.subprocess, 'run', side_effect=spawn):
                response = client.post('/api/resume', json={'run_id': 'old::shell', 'mode': 'background'})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertTrue(result['reopened_terminal'])
                self.assertEqual(result['resume_id'], '')
                args, options = calls[0]
                self.assertEqual(args[-3:], ['terminal', 'Shell-test', temp])
                self.assertEqual(args[args.index('--label') + 1], 'Shell test')
                self.assertEqual(args[args.index('--theme') + 1], 'soft-green')
                self.assertNotIn('--resume-id', args)
                self.assertNotIn('--model', args)
                self.assertEqual(options['cwd'], temp)
                saved = json.loads((Path(result['run_dir']) / 'session.json').read_text())
                self.assertEqual(saved['terminal_theme'], 'soft-green')
                self.assertEqual(saved['linked_folders'][0]['path'], temp)
                self.assertEqual((source_dir / 'history.log').read_text(), 'old history\n')
                self.assertEqual(json.loads((source_dir / 'session.json').read_text()), old_metadata)
                source['alive'] = True
                self.assertEqual(client.post('/api/resume', json={'run_id': 'old::shell'}).status_code, 409)
                self.assertEqual(len(calls), 1)
                source['alive'] = False
                with patch.object(dashboard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'fixture failure')):
                    self.assertEqual(client.post('/api/resume', json={'run_id': 'old::shell'}).status_code, 500)
                self.assertEqual((source_dir / 'history.log').read_text(), 'old history\n')
