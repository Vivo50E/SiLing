"""Background Link owns its source, cancellation, and durable results."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from agent_orchestrator.link_jobs import LinkJobs, ACTIVE
from agent_orchestrator import terminal_files


class LinkJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = LinkJobs(self.root / 'jobs')
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.stop)

    def stop(self):
        self.manager.close()
        for thread in list(self.manager.threads):
            thread.join(3)

    def done(self, run='pane'):
        for _ in range(200):
            job = self.manager.list(run)[0]
            if job['status'] not in ACTIVE:
                return job
            time.sleep(.01)
        self.fail('Link job did not finish')

    def submit(self, extract, register=lambda raw: {'path': raw}, **kwargs):
        return self.manager.submit(kwargs.get('run', 'pane'), {'id': 'context', 'host': 'ssh-alias', 'cwd': '/project'},
                                   kwargs.get('text', 'report.md'), kwargs.get('key', 'request'), extract, register)

    def test_dedupe_binding_results_and_restart(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        def extract(text, cancel):
            gate.wait(2)
            return ['report.md']
        first = self.submit(extract)
        self.assertEqual(self.submit(extract)['id'], first['id'])
        self.assertEqual(self.submit(extract, key='double-click')['id'], first['id'])
        with self.assertRaises(ValueError):
            self.submit(extract, text='different.md')
        self.assertEqual(self.manager.list('other'), [])
        with self.assertRaises(KeyError):
            self.manager.cancel('other', first['id'])
        gate.set()
        job = self.done()
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(job['context']['host'], 'ssh-alias')
        self.assertEqual(job['files'], [{'path': 'report.md'}])
        self.stop()
        restored = LinkJobs(self.root / 'jobs')
        self.addCleanup(restored.close)
        self.assertEqual(restored.list('pane')[0]['id'], first['id'])

    def test_cancel_prevents_registration_and_allows_retry(self):
        started = threading.Event()
        def extract(text, cancel):
            started.set()
            cancel.wait(2)
            return ['report.md']
        registered = []
        first = self.submit(extract, registered.append)
        self.assertTrue(started.wait(1))
        self.manager.cancel('pane', first['id'])
        self.assertEqual(self.done()['status'], 'cancelled')
        self.assertEqual(registered, [])
        self.submit(lambda text, cancel: ['report.md'], registered.append, key='retry')
        self.assertEqual(self.done()['status'], 'completed')
        self.assertEqual(registered, ['report.md'])

    def test_cancel_waits_for_inflight_write_but_prevents_next(self):
        started, release = threading.Event(), threading.Event()
        written = []
        def register(raw):
            started.set()
            release.wait(2)
            written.append(raw)
            return {'path': raw}
        job = self.submit(lambda text, cancel: ['first.md', 'second.md'], register)
        self.assertTrue(started.wait(1))
        cancelled = threading.Event()
        thread = threading.Thread(target=lambda: (self.manager.cancel('pane', job['id']), cancelled.set()))
        thread.start()
        self.assertFalse(cancelled.wait(.05))
        release.set()
        thread.join(2)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.done()['status'], 'cancelled')
        self.assertEqual(written, ['first.md'])

    def test_queue_limits_partial_failures_and_no_raw_error_leak(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        def extract(text, cancel):
            while not gate.wait(.01):
                if cancel.is_set():
                    return []
            return ['report.md']
        for i in range(8):
            self.submit(extract, run=str(i))
        with self.assertRaises(ValueError):
            self.submit(extract, run='overflow')
        self.assertLessEqual(sum(j['status'] == 'running' for j in self.manager.jobs.values()), 2)
        gate.set()
        for i in range(8):
            self.done(str(i))
        def fail(raw):
            raise RuntimeError('secret fixture stderr')
        self.submit(lambda text, cancel: ['a.md', 'b.md'], fail)
        job = self.done()
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(len(job['errors']), 2)
        self.assertNotIn('secret', json.dumps(job))

    def test_queued_cancellation_and_shutdown_do_not_call_extractor(self):
        gates = [threading.Event(), threading.Event()]
        started = [threading.Event(), threading.Event()]
        for i in range(2):
            def extract(text, cancel, index=i):
                started[index].set()
                while not cancel.wait(.01) and not gates[index].is_set():
                    pass
                return []
            self.submit(extract, run=str(i))
        for event in started:
            self.assertTrue(event.wait(1))
        called = []
        job = self.submit(lambda *args: called.append(True) or [], run='queued')
        self.manager.cancel('queued', job['id'])
        self.stop()
        self.assertEqual(called, [])
        self.assertTrue(all(not thread.is_alive() for thread in self.manager.threads))
        self.assertEqual(self.manager.jobs[job['id']]['status'], 'cancelled')

    def test_real_cli_deadline_kills_worker_and_reports_timeout(self):
        script = self.root / 'fake-claude'
        script.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
        script.chmod(0o700)
        start = time.monotonic()
        with patch.object(terminal_files, 'resolve_agent_cli', return_value=str(script)), \
                patch.object(terminal_files, 'MODEL_TIMEOUT_S', .1):
            with self.assertRaisesRegex(ValueError, 'timed out'):
                terminal_files.model_paths('report.md', threading.Event())
        self.assertLess(time.monotonic() - start, 3)

    def test_crashed_jobs_become_interrupted_without_execution(self):
        self.manager.directory.mkdir()
        (self.manager.directory / 'jobs.json').write_text(json.dumps({'old': {'id':'old', 'run_id':'pane', 'status':'running'}}))
        self.assertEqual(self.manager.list('pane')[0]['status'], 'interrupted')
        competing = LinkJobs(self.manager.directory)
        with self.assertRaises(ValueError):
            competing.list('pane')

    def test_real_cli_success_reads_input_and_filters_invented_paths(self):
        script = self.root / 'fake-claude'
        script.write_text('#!/usr/bin/env python3\nimport sys, json\nassert sys.stdin.read() == "reports/test.md"\nassert sys.argv[sys.argv.index("--tools") + 1] == ""\nprint(json.dumps({"structured_output":{"paths":["reports/test.md","invented.md"]}}))\n')
        script.chmod(0o700)
        with patch.object(terminal_files, 'resolve_agent_cli', return_value=str(script)):
            self.assertEqual(terminal_files.model_paths('reports/test.md', threading.Event()), ['reports/test.md'])

    def test_real_cli_cancellation_terminates_worker(self):
        script = self.root / 'fake-claude'
        script.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
        script.chmod(0o700)
        cancel = threading.Event()
        timer = threading.Timer(.2, cancel.set)
        timer.start()
        start = time.monotonic()
        try:
            with patch.object(terminal_files, 'resolve_agent_cli', return_value=str(script)):
                with self.assertRaisesRegex(ValueError, 'cancelled'):
                    terminal_files.model_paths('report.md', cancel)
        finally:
            timer.join()
        self.assertLess(time.monotonic() - start, 3)

class LinkJobAPITests(unittest.TestCase):
    def test_authenticated_worker_links_to_captured_context_without_terminal_input(self):
        from fastapi.testclient import TestClient
        from agent_orchestrator import dashboard
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            report = root / 'report.md'
            report.write_text('fixture report')
            (root / 'session.json').write_text('{}')
            source = {'run_dir':str(root), 'kind':'run', 'tmux_session':'fixture', 'cwd':str(root)}
            with patch.object(dashboard.TtydManager, '_sweep_orphans', return_value=0), \
                    patch.object(dashboard, '_lookup_run_light', side_effect=lambda *_: {**source, **json.loads((root / 'session.json').read_text())}), \
                    patch.object(dashboard, '_is_allowed_linked_folder', return_value=True), \
                    patch.object(terminal_files, 'detect_environment', return_value={'host':'','cwd':str(root),'source':'fixture'}), \
                    patch.object(terminal_files, 'model_paths', return_value=['report.md']), \
                    patch.object(dashboard, 'tmux_send_key') as send:
                app = dashboard.create_app(root, token='fixture-token', ttyd_enabled=False, remote_nodes_enabled=False)
                with TestClient(app) as client:
                    prefix = '/api/sessions/fixture/'
                    headers = {'Authorization':'Bearer fixture-token'}
                    self.assertEqual(client.post(prefix+'link-jobs', json={}).status_code, 401)
                    context = client.get(prefix+'file-context', headers=headers).json()['current']
                    body = {'text':'report.md','context_id':context['id'],'request_id':'fixture-request'}
                    response = client.post(prefix+'link-jobs', headers=headers, json=body)
                    self.assertEqual(response.status_code, 200, response.text)
                    job_id = response.json()['id']
                    for _ in range(100):
                        job = client.get(prefix+'link-jobs', headers=headers).json()['jobs'][0]
                        if job['status'] not in ACTIVE:
                            break
                        time.sleep(.01)
                    self.assertEqual(job['status'], 'completed', job)
                    self.assertEqual(job['files'][0]['source_path'], str(report))
                    self.assertEqual(client.post(prefix+'link-jobs', headers=headers, json=body).json()['id'], job_id)
                    folders = client.get(prefix+'folders', headers=headers).json()['folders']
                    self.assertEqual(len(folders), 1)
                    self.assertEqual(folders[0]['path'], str(report))
                    self.assertEqual(client.post('/api/sessions/other/link-jobs/'+job_id+'/cancel', headers=headers).status_code, 404)
                    self.assertEqual(client.post(prefix+'discover-files', headers=headers,
                                                 json={**body, 'intelligent':True}).status_code, 400)
                    # A queued SSH task keeps its chosen host even after the pane context changes.
                    remote = client.put(prefix+'file-context', headers=headers,
                                        json={'mode':'ssh','host':'fixture-host','cwd':'/remote/project'}).json()['current']
                    release = threading.Event()
                    def extract(text, cancel):
                        release.wait(2)
                        return ['report.md']
                    with patch.object(terminal_files, 'model_paths', side_effect=extract), \
                            patch.object(dashboard, 'fetch_ssh_preview', return_value=report) as fetch:
                        response = client.post(prefix+'link-jobs', headers=headers,
                                               json={**body, 'context_id':remote['id'], 'request_id':'remote-request'})
                        self.assertEqual(response.status_code, 200, response.text)
                        client.put(prefix+'file-context', headers=headers, json={'mode':'local','cwd':str(root)})
                        release.set()
                        for _ in range(100):
                            job = client.get(prefix+'link-jobs', headers=headers).json()['jobs'][0]
                            if job['status'] not in ACTIVE:
                                break
                            time.sleep(.01)
                        self.assertEqual(job['status'], 'completed', job)
                        self.assertEqual(fetch.call_args.args[:2], ('fixture-host','/remote/project/report.md'))
                    send.assert_not_called()
