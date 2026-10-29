"""Discovery must not search old transcripts just to update live activity."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_orchestrator import dashboard


class DiscoveryResourcesTests(unittest.TestCase):
    def test_activity_resolves_only_live_codex_transcripts(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp)
            for name, agent in [('live-code', 'codex'), ('old-code', 'codex'),
                                ('live-claude', 'claude'), ('live-cursor', 'cursor')]:
                folder = root / name
                folder.mkdir()
                (folder / 'session.json').write_text(json.dumps({
                    'name': name, 'label': name, 'agent': agent,
                    'tmux_session': name, 'resume_id': name,
                    'started_at': '2026-10-01T00:00:00',
                }))
            stack.enter_context(patch.object(dashboard, 'tmux_list_sessions',
                return_value=['live-code', 'live-claude', 'live-cursor']))
            stack.enter_context(patch.object(dashboard, '_auto_title_for', return_value=''))
            stack.enter_context(patch.object(dashboard, '_probe_session_activity', return_value={}))
            stack.enter_context(patch.object(dashboard, '_record_activity_timeline_snapshot'))
            resolver = stack.enter_context(patch.object(dashboard, '_conversation_transcript_path',
                                                        return_value=Path('/fixture/transcript.jsonl')))
            service = Mock()
            rows = dashboard._discover_runs(root, service)
            self.assertEqual(len(rows), 4, 'Historical rows remain available in the UI')
            self.assertEqual([c.args[0]['tmux_session'] for c in resolver.call_args_list], ['live-code'])
            registered = {r['tmux_session']: r for r in service.register_runs.call_args.args[0]}
            self.assertEqual(len(registered), 4, 'Canonical conversation aliases are preserved')
            self.assertEqual(registered['live-code']['_native_transcript_path'], '/fixture/transcript.jsonl')
            for name in ['old-code', 'live-claude', 'live-cursor']:
                self.assertEqual(registered[name]['_native_transcript_path'], '')
