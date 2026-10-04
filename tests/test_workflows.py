import copy
import json
from pathlib import Path
import tempfile
import unittest

from agent_orchestrator.workflows import Workflows, validate


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name in ('implement', 'test', 'review'):
            (self.root / name).mkdir()
        self.manager = Workflows(self.root)
        self.spec = {'name': 'Fixture', 'max_concurrent': 2, 'nodes':
            [{'id': name, 'cwd': str(self.root / name), 'agent': 'codex',
             'prompt': 'Produce an explicit report', 'depends_on': deps}
            for name, deps in [('implement', []), ('test', ['implement']), ('review', ['test'])]]
            + [{'id': 'approve', 'kind': 'approval', 'depends_on': ['review']}]}
        self.spawns = []
        self.live = {}

    def spawn(self, body):
        self.spawns.append(copy.deepcopy(body))
        rid = 'child-' + str(len(self.spawns))
        self.live[rid] = {'alive': True}
        return {'run_id': rid}

    def resolve(self, ref, deliverable):
        if ref['artifact_id'] == 'artifact-missing':
            raise ValueError('Artifact missing')
        return {**ref, 'path': '/fixture/report.txt'}

    def start(self):
        return self.manager.start(self.spec, 'request', self.spawn, self.resolve)

    def action(self, run, node, action, stop=None):
        return self.manager.action(run['id'], node, action, self.spawn, self.resolve, self.live.get, stop)

    def report(self, run, node, **body):
        return self.manager.report(run['id'], node, body, self.spawn, self.resolve)

    def test_fixed_graph_requires_outputs_and_explicit_approval(self):
        run = self.start()
        self.assertEqual(len(self.spawns), 1)
        again = self.start()
        self.assertEqual(again['id'], run['id'])
        self.assertEqual(len(self.spawns), 1)
        for i, name in enumerate(('implement', 'test', 'review'), 1):
            with self.assertRaises(ValueError):
                self.report(run, name, run_id=f'child-{i}', artifacts=[])
            run = self.report(run, name, run_id=f'child-{i}', artifacts=['artifact-report'])
        self.assertEqual(run['nodes']['approve']['status'], 'awaiting_approval')
        self.assertEqual(run['status'], 'running')
        run = self.action(run, 'approve', 'approve')
        self.assertEqual(run['status'], 'succeeded')
        self.assertEqual(len(self.spawns), 3)
        self.assertIn('child-1', self.spawns[1]['prompt'])
        self.assertIn('artifact-report', self.spawns[1]['prompt'])

    def test_preflight_rejection_is_failed_and_retryable_without_unknown_process(self):
        from agent_orchestrator.workflows import DispatchRejected
        def rejected(body):
            raise DispatchRejected('Workspace trust has not been accepted')
        run = self.manager.start(self.spec, 'request', rejected, self.resolve)
        self.assertEqual(run['nodes']['implement']['status'], 'failed')
        self.assertEqual(run['status'], 'failed')
        run = self.action(run, 'implement', 'retry')
        self.assertEqual(run['nodes']['implement']['status'], 'running')
        self.assertEqual(len(self.spawns), 1)

    def test_invalid_graph_and_missing_inputs_never_spawn(self):
        for mutation in ('cycle', 'unknown', 'duplicate', 'overlap', 'missing'):
            spec = copy.deepcopy(self.spec)
            if mutation == 'cycle': spec['nodes'][0]['depends_on'] = ['review']
            if mutation == 'unknown': spec['nodes'][0]['depends_on'] = ['unknown']
            if mutation == 'duplicate': spec['nodes'][1]['id'] = 'implement'
            if mutation == 'overlap': spec['nodes'][1]['cwd'] = spec['nodes'][0]['cwd']
            if mutation == 'missing': spec['nodes'][0]['inputs'] = [{'session_id':'old','artifact_id':'artifact-missing'}]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.manager.start(spec, mutation, self.spawn, self.resolve)
        self.assertEqual(self.spawns, [])

    def test_failure_blocks_descendants_and_retry_only_replaces_failed_attempt(self):
        run = self.start()
        with self.assertRaises(ValueError):
            self.report(run, 'implement', run_id='different', artifacts=['artifact-report'])
        run = self.report(run, 'implement', run_id='child-1', failed=True, reason='test failed')
        self.assertEqual(run['nodes']['test']['status'], 'blocked')
        with self.assertRaises(ValueError):
            self.action(run, 'implement', 'retry')
        self.live['child-1']['alive'] = False
        run = self.action(run, 'implement', 'retry')
        self.assertEqual(run['nodes']['implement']['attempt'], 2)
        self.assertEqual(run['nodes']['implement']['history'][0]['run_id'], 'child-1')
        with self.assertRaises(ValueError):
            self.report(run, 'implement', run_id='child-1', artifacts=['artifact-report'])
        self.assertEqual(len(self.spawns), 2)

    def test_restart_does_not_spawn_and_ended_child_requires_reconciliation(self):
        run = self.start()
        other = Workflows(self.root)
        self.assertEqual(other.list()[0]['nodes']['implement']['run_id'], 'child-1')
        self.assertEqual(len(self.spawns), 1)
        self.live['child-1']['alive'] = False
        run = self.action(run, 'implement', 'reconcile')
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(len(self.spawns), 1)

    def test_uncertain_spawn_is_durable_and_cannot_be_retried(self):
        def crash(body):
            raise RuntimeError('transport interrupted')
        run = self.manager.start(self.spec, 'request', crash, self.resolve)
        self.assertEqual(run['nodes']['implement']['status'], 'starting')
        self.assertEqual(Workflows(self.root).list()[0]['nodes']['implement']['status'], 'starting')
        with self.assertRaises(ValueError):
            self.action(run, 'implement', 'retry')
        self.assertEqual(self.start()['id'], run['id'])
        self.assertEqual(self.spawns, [])

    def test_cancellation_stops_only_owned_attempt_and_does_not_advance(self):
        run = self.start()
        calls = []
        def stop(*args):
            calls.append(args)
            return True
        run = self.action(run, 'implement', 'cancel', stop)
        self.assertEqual(calls[0][:3], ('child-1', run['id'], 'implement'))
        self.assertEqual(run['nodes']['implement']['status'], 'cancelled')
        self.assertEqual(run['nodes']['test']['status'], 'blocked')
        self.assertEqual(len(self.spawns), 1)

    def test_concurrency_limit_and_workspace_reservations(self):
        for node in self.spec['nodes'][:3]: node['depends_on'] = []
        run = self.start()
        self.assertEqual(len(self.spawns), 2)
        with self.assertRaises(ValueError):
            self.manager.start(self.spec, 'other-request', self.spawn, self.resolve)
        self.report(run, 'implement', run_id='child-1', artifacts=['artifact-report'])
        self.assertEqual(len(self.spawns), 3)

    def test_changed_input_blocks_dispatch_and_retains_completed_result(self):
        run = self.start()
        def missing(ref, deliverable):
            if not deliverable: raise ValueError('File removed after success report')
            return ref
        run = self.manager.report(run['id'], 'implement', {'run_id':'child-1', 'artifacts':['artifact-report']}, self.spawn, missing)
        self.assertEqual(run['nodes']['implement']['status'], 'succeeded')
        self.assertEqual(run['nodes']['test']['status'], 'failed')
        self.assertEqual(len(self.spawns), 1)

    def test_uncertain_start_reconciles_exact_attempt_without_duplicate_spawn(self):
        def lost_reply(body):
            self.spawn(body)
            raise RuntimeError('Lost reply after delegate started')
        run = self.manager.start(self.spec, 'request', lost_reply, self.resolve)
        token = run['nodes']['implement']['attempt_token']
        calls = []
        def find(workflow_id, node_id, attempt):
            calls.append((workflow_id, node_id, attempt))
            return {'run_id':'child-1','alive':True}
        restored = Workflows(self.root)
        run = restored.action(run['id'], 'implement', 'reconcile', self.spawn, self.resolve, self.live.get, find_attempt=find)
        self.assertEqual(calls, [(run['id'],'implement',token)])
        self.assertEqual(run['nodes']['implement']['run_id'], 'child-1')
        self.assertEqual(run['nodes']['implement']['status'], 'running')
        self.assertEqual(len(self.spawns), 1)


class WorkflowAPITests(unittest.TestCase):
    def test_authenticated_report_requires_current_execution_verified_deliverable_and_approval(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from agent_orchestrator import dashboard, artifacts
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            work = root/'work'; work.mkdir()
            report = work/'report.txt'; report.write_text('Verified fixture result')
            record = {'path':str(report), 'type':'file', 'label':'Report'}
            record['artifact'] = artifacts.metadata(record, {'run_id':'child'}, purpose='reference')
            meta = root/'session.json';meta.write_text(json.dumps({'linked_folders':[record]}))
            def lookup(directory, run_id):
                if run_id != 'child': return None
                return {'run_id':'child', 'kind':'run', 'run_dir':str(root), **json.loads(meta.read_text())}
            manager = Workflows(root)
            run = manager.start({'nodes':[
                {'id':'implement', 'cwd':str(work), 'prompt':'Fixture'},
                {'id':'approval','kind':'approval','depends_on':['implement']}]}, 'api-fixture', lambda body:{'run_id':'child'}, lambda *args:None)
            with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0), \
                    patch.object(dashboard, '_lookup_run_light', side_effect=lookup), \
                    patch.object(dashboard, '_is_allowed_linked_folder', return_value=True):
                app = dashboard.create_app(root, token='fixture', ttyd_enabled=False, remote_nodes_enabled=False)
                client = TestClient(app)
                self.addCleanup(client.close)
                headers = {'Authorization':'Bearer fixture'}
                path = f'/api/workflows/{run["id"]}/implement/report'
                body = {'run_id':'child','artifacts':[record['artifact']['id']]}
                self.assertEqual(client.post(path, json=body).status_code, 401)
                self.assertEqual(client.post(path, json=body, headers=headers).status_code, 400)
                role = client.patch(f'/api/sessions/child/artifacts/{record["artifact"]["id"]}', json={'purpose':'deliverable'}, headers=headers)
                self.assertEqual(role.status_code, 200)
                report.unlink()
                self.assertEqual(client.post(path, json=body, headers=headers).status_code, 400)
                report.write_text('Restored fixture evidence')
                result = client.post(path, json=body, headers=headers)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()['nodes']['approval']['status'], 'awaiting_approval')
                self.assertEqual(client.post(path, json=body, headers=headers).status_code, 400)
                result = client.post(f'/api/workflows/{run["id"]}/approval/approve', json={}, headers=headers)
                self.assertEqual(result.json()['status'], 'succeeded')
                self.assertEqual(len(client.get('/api/workflows', headers=headers).json()['workflows']), 1)
