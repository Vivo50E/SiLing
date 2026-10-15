"""Recovery must not confuse launch defaults, native choices and tool output."""
import json
from pathlib import Path
import tempfile
import unittest
from agent_orchestrator import dashboard


class RecoveryModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'conversation.jsonl'
        self.row = {'agent': 'claude', 'resume_id': 'conversation',
                    'model': 'launch-model', 'effort': 'high', 'effort_mode': 'fixed',
                    'started_at': '2026-10-15T10:00:00Z',
                    'resume': {'source_path': str(self.path)}}

    def model(self, records):
        self.path.write_text('\n'.join(json.dumps(record) for record in records))
        return dashboard._run_with_recovery_model(self.row)['model']

    def record(self, model, timestamp='2026-10-15T11:00:00Z', **extra):
        return {'type': 'assistant', 'timestamp': timestamp, 'message': {'model': model}, **extra}

    def test_only_primary_model_records_override_launch_model(self):
        records = [self.record('current-model'),
                   self.record('side-model', '2026-10-15T12:00:00Z', isSidechain=True),
                   self.record('other-model', '2026-10-15T13:00:00Z', sessionId='other'),
                   self.record('tool-model', '2026-10-15T14:00:00Z', type='user'),
                   self.record('<synthetic>', '2026-10-15T15:00:00Z'),
                   self.record('invalid-date-model', 123), None, ['invalid']]
        self.assertEqual(self.model(records), 'current-model')

    def test_old_history_and_newer_non_model_events_cannot_revert_selection(self):
        self.assertEqual(self.model([self.record('old', '2026-10-15T09:00:00Z'),
            {'type': 'system', 'timestamp': '2026-10-15T12:00:00Z'}]), 'launch-model')

    def test_timestamp_order_not_file_order_selects_latest_model(self):
        self.assertEqual(self.model([self.record('latest', '2026-10-15T12:00:00Z'),
                                    self.record('earlier')]), 'latest')

    def test_native_selection_after_dashboard_change_wins(self):
        self.row['runtime_config_updated_at'] = '2026-10-15T10:30:00Z'
        self.assertEqual(self.model([self.record('native-new')]), 'native-new')

    def test_missing_transcript_keeps_saved_model(self):
        self.assertEqual(dashboard._run_with_recovery_model(self.row)['model'], 'launch-model')

    def test_cursor_does_not_use_claude_or_codex_model_recovery(self):
        self.row['agent'] = 'cursor'
        self.assertEqual(self.model([self.record('different')]), 'launch-model')

    def test_runtime_change_timestamp_survives_discovery(self):
        row = {}
        dashboard._add_resume_fields(row, {'runtime_config_updated_at': '2026-10-15T12:00:00Z'})
        self.assertEqual(row['runtime_config_updated_at'], '2026-10-15T12:00:00Z')
