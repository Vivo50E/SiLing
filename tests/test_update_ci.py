import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_orchestrator import update_ci
from agent_orchestrator.self_update import SelfUpdateManager


class UpdateCITests(unittest.TestCase):
    def setUp(self):
        self.commit = 'a' * 40
        self.repository = 'example/SiLing'
        self.run = {'id': 12, 'run_attempt': 2, 'head_sha': self.commit, 'head_branch': 'main',
                    'event': 'push', 'path': '.github/workflows/ci.yml', 'status': 'completed',
                    'conclusion': 'success', 'head_repository': {'full_name': self.repository}}
        self.jobs = [{'name': name, 'head_sha': self.commit, 'status': 'completed', 'conclusion': 'success',
                      'steps': [{'name': update_ci.FULL_SUITE_STEP, 'status': 'completed', 'conclusion': 'success'}]}
                     for name in sorted(update_ci.REQUIRED_JOBS)]

    def check(self, run=None, jobs=None, latest=None):
        rows = self.jobs if jobs is None else jobs
        with patch.object(update_ci, 'github_json', side_effect=[
                {'workflow_runs': [run or self.run]}, {'jobs': rows, 'total_count': len(rows)}, latest or self.run]) as api:
            result = update_ci.verified_ci(self.repository, self.commit, 'main')
            return result, api

    def test_exact_commit_requires_full_python_matrix_desktop_and_latest_attempt(self):
        result, api = self.check()
        self.assertEqual(result['head'], self.commit)
        self.assertEqual(result['url'], 'https://github.com/example/SiLing/actions/runs/12')
        self.assertIn('/attempts/2/jobs?', api.call_args_list[1].args[0])
        self.assertEqual(api.call_count, 3)

    def test_foreign_stale_incomplete_and_wrong_workflow_runs_are_rejected(self):
        for field, value in [('head_sha', 'b'*40), ('head_branch', 'other'), ('event', 'pull_request'),
                             ('path', '.github/workflows/other.yml'), ('status', 'in_progress'),
                             ('conclusion', 'failure'), ('head_repository', {'full_name': 'foreign/SiLing'}),
                             ('id', '12'), ('run_attempt', 0)]:
            with self.subTest(field=field):
                result, _ = self.check(run={**self.run, field: value})
                self.assertIsNone(result)

    def test_missing_skipped_failed_and_partial_full_suite_steps_are_rejected(self):
        for field, value in [('status', 'queued'), ('conclusion', 'skipped'), ('conclusion', 'failure'),
                             ('head_sha', 'b'*40), ('steps', [])]:
            rows = copy.deepcopy(self.jobs)
            rows[1][field] = value
            with self.subTest(field=field, value=value):
                self.assertIsNone(self.check(jobs=rows)[0])
        self.assertIsNone(self.check(jobs=self.jobs[:2])[0])
        rows = copy.deepcopy(self.jobs)
        rows[1]['steps'][0]['conclusion'] = 'skipped'
        self.assertIsNone(self.check(jobs=rows)[0])

    def test_rerun_and_unavailable_or_malformed_evidence_never_become_success(self):
        self.assertIsNone(self.check(latest={**self.run, 'run_attempt': 3})[0])
        self.assertIsNone(self.check(latest={**self.run, 'status': 'queued'})[0])
        for response in ({}, {'workflow_runs': []}, {'workflow_runs': [None]}):
            with patch.object(update_ci, 'github_json', return_value=response):
                self.assertIsNone(update_ci.verified_ci(self.repository, self.commit, 'main'))
        with patch.object(update_ci, 'github_json', side_effect=subprocess.TimeoutExpired('gh', 8)):
            self.assertIsNone(update_ci.verified_ci(self.repository, self.commit, 'main'))

    def test_only_explicit_github_repository_urls_are_supported(self):
        for url in ('https://github.com/example/SiLing.git', 'git@github.com:example/SiLing.git',
                    'ssh://git@github.com/example/SiLing.git'):
            self.assertEqual(update_ci.github_repository(url), self.repository)
        for url in ('https://github.com.evil/example/SiLing', 'https://token@github.com/example/SiLing',
                    'https://github.com/example/SiLing?token=private', '/local/repository', 'git@gitlab.com:example/repo.git'):
            self.assertEqual(update_ci.github_repository(url), '')

    def test_changed_workflow_dependencies_or_runner_force_full_local_tests(self):
        manager = SelfUpdateManager(Path('/fixture'))
        candidate = {'kind': 'upstream', 'source': 'origin/main', 'target_head': 'b'*40, 'head': self.commit}
        def git(*args, **kwargs):
            stdout = 'https://github.com/example/SiLing.git' if args[0] == 'remote' else 'same content'
            return subprocess.CompletedProcess(args, 0, stdout, '')
        with patch.object(manager, '_git', side_effect=git), \
                patch('agent_orchestrator.self_update.verified_ci', return_value={'head': self.commit}) as lookup:
            self.assertIsNotNone(manager._ci_evidence(candidate))
            lookup.assert_called_once_with(self.repository, self.commit, 'main')
        for path in ('requirements.txt', '.github/workflows/ci.yml', 'Makefile', 'tools/check.py'):
            def changed(*args, **kwargs):
                result = git(*args, **kwargs)
                if args[0] == 'show' and args[1] == self.commit + ':' + path:
                    result.stdout = 'changed content'
                return result
            with self.subTest(path=path), patch.object(manager, '_git', side_effect=changed), \
                    patch('agent_orchestrator.self_update.verified_ci') as lookup:
                self.assertIsNone(manager._ci_evidence(candidate))
                lookup.assert_not_called()

    def test_gh_requests_pin_hostname_and_do_not_use_returned_urls(self):
        module = Mock()
        module.run.return_value = subprocess.CompletedProcess([], 0, '{"jobs": []}', '')
        with patch.object(update_ci, 'subprocess', module):
            self.assertEqual(update_ci.github_json('repos/example/SiLing/actions/runs/12'), {'jobs': []})
        self.assertEqual(module.run.call_args.args[0][:4], ['gh', 'api', '--hostname', 'github.com'])
        self.assertEqual(module.run.call_args.kwargs['timeout'], 8)

    def test_api_passes_full_option_and_rejects_non_boolean_values(self):
        from fastapi.testclient import TestClient
        from agent_orchestrator import dashboard
        with tempfile.TemporaryDirectory() as directory:
            app = dashboard.create_app(Path(directory), token='fixture', remote_nodes_enabled=False)
            headers = {'Authorization': 'Bearer fixture', 'X-Orch-Self-Update': 'reviewed'}
            with TestClient(app) as client, patch.object(app.state.self_updates, 'verify', return_value={'ok': False}) as verify:
                response = client.post('/api/self-update/verify', headers=headers,
                                       json={'branch': 'upstream:origin/main', 'full': True})
                self.assertEqual(response.status_code, 200)
                verify.assert_called_once_with('upstream:origin/main', full=True)
                verify.reset_mock()
                for body in ({'branch': 'upstream:origin/main', 'full': 'false'}, []):
                    self.assertEqual(client.post('/api/self-update/verify', headers=headers, json=body).status_code, 400)
                verify.assert_not_called()
