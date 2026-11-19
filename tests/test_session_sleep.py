import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class SessionSleepTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.path = self.root / 'session.json'
        self.path.write_text(json.dumps({'agent':'claude','resume_id':'saved-id','label':'Keep title','model':'keep-model'}))
        self.row = dict(kind='run',run_id='fixture',run_dir=str(self.root),task='agent',agent='claude',
                        tmux_session='sleep-fixture',alive=True,status='running')
        self.live = True
        self.stack.enter_context(patch.dict(os.environ, {'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0','ORCH_DASHBOARD_CONFIG':str(self.root/'none')}))
        self.stack.enter_context(patch.object(dashboard, '_lookup_run', side_effect=lambda *a:self.row))
        self.stack.enter_context(patch.object(dashboard, 'tmux_alive', side_effect=lambda *a:self.live))
        self.stack.enter_context(patch.object(dashboard, 'tmux_capture', return_value='fixture'))
        self.discovery = self.stack.enter_context(patch.object(dashboard, '_discover_resume_metadata', return_value={'resume_agent':'claude','resume_id':'saved-id'}))
        self.stop = self.stack.enter_context(patch.object(dashboard, '_graceful_stop_agent', return_value={'ok':True}))
        self.kill = self.stack.enter_context(patch.object(dashboard, 'tmux_kill', side_effect=self.kill_session))
        self.stack.enter_context(patch.object(dashboard, 'kill_shadow_session'))
        self.reap = self.stack.enter_context(patch.object(dashboard.TtydManager, 'reap_dead'))
        self.app = dashboard.create_app(self.root, token='fixture', ttyd_enabled=False,remote_nodes_enabled=False)
        self.client = TestClient(self.app);self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer fixture'}
    def kill_session(self, *args):
        self.live=False;return True
    def sleep(self):
        return self.client.post('/api/sessions/fixture/sleep', headers=self.headers)
    def test_sleep_preserves_recovery_and_releases_wrapper(self):
        response=self.sleep();self.assertEqual(response.status_code,200,response.text)
        record=json.loads(self.path.read_text())
        self.assertEqual(record['status'],'sleeping');self.assertEqual(record['resume_id'],'saved-id')
        self.assertEqual(record['label'],'Keep title');self.assertEqual(record['model'],'keep-model')
        self.kill.assert_called_once();self.reap.assert_called_once_with(min_interval_s=0)
        self.row['status']='sleeping';self.assertEqual(self.sleep().status_code,200)
        self.kill.assert_called_once()
    def test_missing_identity_never_stops_agent(self):
        self.discovery.return_value={}
        self.assertEqual(self.sleep().status_code,409);self.stop.assert_not_called();self.kill.assert_not_called()
    def test_stop_failure_keeps_pane_active_without_force(self):
        self.stop.return_value={'ok':False,'reason':'still working'}
        self.assertEqual(self.sleep().status_code,409);self.kill.assert_not_called()
        self.assertNotEqual(json.loads(self.path.read_text()).get('status'),'sleeping')
    def test_wrapper_failure_is_not_reported_as_sleeping(self):
        self.kill.side_effect=lambda *a:False
        self.assertEqual(self.sleep().status_code,409)
        self.assertNotEqual(json.loads(self.path.read_text()).get('status'),'sleeping')
    def test_terminal_does_not_require_conversation(self):
        self.row['agent']='terminal';self.discovery.return_value={}
        self.assertEqual(self.sleep().status_code,200)
        self.assertEqual(json.loads(self.path.read_text())['status'],'sleeping')
    def test_task_changes_only_target_record(self):
        self.row['kind']='task';path=self.root/'state.json'
        path.write_text(json.dumps({'agent':{'label':'Keep'},'other':{'status':'running'}}))
        self.assertEqual(self.sleep().status_code,200)
        data=json.loads(path.read_text());self.assertEqual(data['agent']['status'],'sleeping')
        self.assertEqual(data['other'],{'status':'running'})
    def test_auth_and_unsupported_are_non_destructive(self):
        self.assertEqual(self.client.post('/api/sessions/fixture/sleep').status_code,401)
        self.row['kind']='orphan';self.assertEqual(self.sleep().status_code,409)
        self.row['kind']='run';self.row['agent']='custom';self.assertEqual(self.sleep().status_code,409)
        self.stop.assert_not_called()
