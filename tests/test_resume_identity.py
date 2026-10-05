"""Stopping a pane must preserve its native conversation, even in a shared cwd."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class ResumeIdentityTests(unittest.TestCase):
    def test_saved_identity_wins_over_other_conversation_in_terminal_or_directory(self):
        for agent in ('codex', 'claude', 'cursor'):
            with self.subTest(agent=agent):
                saved = dashboard._build_resume_meta(agent, 'original', 'orchestrator-resume', confidence='exact')
                other = dashboard._build_resume_meta(agent, 'other', 'terminal')
                row = {'agent': agent, 'cwd': '/shared/project', **saved}
                with patch.object(dashboard, '_extract_resume_from_text', return_value=other), patch.object(dashboard, '_find_' + agent + '_resume', return_value=other):
                    self.assertEqual(dashboard._discover_resume_metadata(row, 'another resume command'), {**saved, 'resume_source_path': ''})

    def test_unidentified_session_still_discovers_identity(self):
        meta = dashboard._build_resume_meta('codex', 'new', 'terminal')
        with patch.object(dashboard, '_extract_resume_from_text', return_value=meta):
            self.assertEqual(dashboard._discover_resume_metadata({'agent': 'codex'}, 'output'), meta)

    def test_stop_and_kill_keep_saved_identity_on_disk(self):
        for action in ('stop', 'kill'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
                root = Path(temp)
                saved = dashboard._build_resume_meta('codex', 'original', 'orchestrator-resume', confidence='exact')
                row = {'agent': 'codex', 'kind': 'run', 'run_dir': temp, 'cwd': temp,
                       'tmux_session': 'fixture', **saved}
                (root / 'session.json').write_text(json.dumps(row))
                stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE': '0', 'ORCH_DASHBOARD_CONFIG': str(root / 'missing')}))
                stack.enter_context(patch.object(dashboard, '_lookup_run', return_value=row))
                stack.enter_context(patch.object(dashboard, 'tmux_alive', return_value=True))
                stack.enter_context(patch.object(dashboard, 'tmux_capture', return_value=''))
                stack.enter_context(patch.object(dashboard, '_find_codex_resume', return_value=dashboard._build_resume_meta('codex', 'other', 'codex-session-file')))
                stack.enter_context(patch.object(dashboard, '_graceful_stop_agent', return_value={'ok': True}))
                stack.enter_context(patch.object(dashboard, 'tmux_kill', return_value=True))
                stack.enter_context(patch.object(dashboard, 'kill_shadow_session'))
                app = dashboard.create_app(root / 'outputs', token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
                client = TestClient(app)
                stack.callback(client.close)
                response = client.post('/api/sessions/source/' + action, headers={'Authorization': 'Bearer fixture'})
                self.assertEqual(response.status_code, 200, response.text)
                data = json.loads((root / 'session.json').read_text())
                self.assertEqual(data['resume_id'], 'original')
                self.assertEqual(data['native_resume']['current_id'], 'original')
                self.assertEqual(data['resume']['id'], 'original')
                self.assertEqual(data['resume_confidence'], 'exact')
