import json
from pathlib import Path
import tempfile
import unittest
from agent_orchestrator import dashboard, session_lifecycle as life


class LifecycleTests(unittest.TestCase):
    def test_live_evidence_overrides_stale_saved_working_event(self):
        row = {'run_id':'one','alive':True,'busy':True,'native_activity':{'state':'working','source':'claude-hook','updated_at':100}}
        self.assertEqual(life.project(row)['execution'], 'working')
        self.assertEqual(life.project({**row,'alive':False})['execution'], 'ended')
        offline = life.project({**row,'remote':True,'node_online':False})
        self.assertEqual(offline['execution'], 'unknown')
        self.assertEqual(offline['connection'], 'offline')
        self.assertEqual(offline['recovery'], 'reconnect')

    def test_native_waiting_beats_terminal_activity_and_inference_is_labelled(self):
        row = {'alive':True,'busy':True,'native_activity':{'state':'needs_input','source':'claude-hook'}}
        state = life.project(row)
        self.assertEqual(state['attention'], 'needs_input')
        self.assertFalse(state['inferred'])
        self.assertTrue(life.project({'alive':True,'busy':True})['inferred'])

    def test_resume_lineage_survives_multiple_attempts_and_native_id_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'session.json'
            path.write_text('{}')
            source = {'run_id':'first','agent':'terminal'}
            self.assertEqual(life.record_resume(source, {'run_dir':temp}), '')
            saved = json.loads(path.read_text())
            row = {'run_id':'second'}
            dashboard._add_resume_fields(row, saved)
            self.assertEqual(life.identity(source)['logical_session_id'], life.identity(row)['logical_session_id'])
            self.assertEqual(life.record_resume(row, {'run_dir':temp}), '')
            third = {'run_id':'third','resume_id':'new-native-id', **json.loads(path.read_text())}
            self.assertEqual(life.identity(third)['logical_session_id'], life.identity(source)['logical_session_id'])
            self.assertEqual(life.identity(third)['previous_execution_id'], 'second')
            self.assertNotEqual(life.identity(third)['execution_id'], life.identity(source)['execution_id'])

    def test_remote_lineage_uses_owner_identity_and_is_namespaced(self):
        owner = life.project({'run_id':'original','alive':True})
        remote = {'remote':True,'node_id':'one','run_id':'remote-original','lifecycle':owner}
        before = life.identity(remote)['logical_session_id']
        after = life.identity({**remote,'run_id':'remote-resumed','logical_session_id':owner['logical_session_id']})
        self.assertEqual(after['logical_session_id'], before)
        self.assertNotEqual(life.identity({**remote,'node_id':'two'})['logical_session_id'], before)

    def test_manual_priority_attention_and_terminal_activity_are_distinct(self):
        state = life.project({'alive':True,'panel_state':'p0','native_activity':{'state':'needs_input'}})
        self.assertEqual(state['priority'], 'p0')
        self.assertEqual(state['attention'], 'needs_input')
        blocked = life.project({'alive':True,'panel_state':'blocked'})
        self.assertEqual(blocked['priority'], '')
        self.assertEqual(blocked['attention'], 'blocked')
        terminal = life.project({'alive':True,'agent':'terminal','busy':True})
        self.assertEqual(terminal['execution'], 'terminal_active')
        self.assertTrue(terminal['inferred'])
