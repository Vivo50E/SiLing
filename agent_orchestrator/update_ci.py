"""Bounded, read-only GitHub CI evidence for an exact upstream commit."""
from __future__ import annotations

import json
import re
import subprocess


REQUIRED_JOBS = {'test (3.10)', 'test (3.13)', 'desktop'}
FULL_SUITE_STEP = 'Validate workspace and run the full suite'


def github_repository(url: str) -> str:
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', url.strip())
    if not match or any(part in {'.', '..'} for part in match[1].split('/')):
        return ''
    return match[1]


def github_json(endpoint: str) -> dict:
    # Never use a provider-returned URL, ambient GH_HOST or a shell command.
    result = subprocess.run(['gh', 'api', '--hostname', 'github.com', endpoint],
                            capture_output=True, text=True, timeout=8, check=True)
    if len(result.stdout) > 262144:
        raise ValueError('CI response too large')
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError('Invalid CI response')
    return data


def verified_ci(repository: str, commit: str, branch: str) -> dict | None:
    """Reject stale, partial, skipped, rerun or foreign-repository evidence."""
    if branch != 'main' or not re.fullmatch(r'[0-9a-f]{40}', commit):
        return None
    try:
        response = github_json(f'repos/{repository}/actions/workflows/ci.yml/runs?head_sha={commit}&event=push&branch=main&per_page=1')
        runs = response.get('workflow_runs', [])
        if not isinstance(runs, list) or not runs:
            return None
        run = runs[0]
        if (run.get('head_sha') != commit or run.get('head_branch') != branch
                or run.get('event') != 'push' or run.get('path') != '.github/workflows/ci.yml'
                or run.get('status') != 'completed' or run.get('conclusion') != 'success'
                or str(run.get('head_repository', {}).get('full_name', '')).lower() != repository.lower()):
            return None
        run_id, attempt = run.get('id'), run.get('run_attempt')
        if type(run_id) is not int or type(attempt) is not int or run_id < 1 or attempt < 1:
            return None
        response = github_json(f'repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100')
        jobs = response.get('jobs', [])
        if not isinstance(jobs, list) or response.get('total_count') != len(jobs) or len(jobs) > 100:
            return None
        if not REQUIRED_JOBS <= {job.get('name') for job in jobs}:
            return None
        for job in jobs:
            if (job.get('head_sha') != commit or job.get('status') != 'completed'
                    or job.get('conclusion') != 'success'):
                return None
            if job['name'].startswith('test (') and not any(
                    step.get('name') == FULL_SUITE_STEP and step.get('status') == 'completed'
                    and step.get('conclusion') == 'success' for step in job.get('steps', [])):
                return None
        # Check the latest attempt again; never mix successful jobs with a
        # concurrently requested rerun or a newer failed attempt.
        latest = github_json(f'repos/{repository}/actions/runs/{run_id}')
        if (latest.get('run_attempt') != attempt or latest.get('head_sha') != commit
                or latest.get('status') != 'completed' or latest.get('conclusion') != 'success'):
            return None
        return {'repository': repository, 'head': commit, 'run_id': run_id, 'attempt': attempt,
                'url': f'https://github.com/{repository}/actions/runs/{run_id}',
                'jobs': sorted(REQUIRED_JOBS)}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError, KeyError):
        return None


LOCAL_SMOKE = r'''
import os, sys, tempfile, unittest
from pathlib import Path
import yaml, fastapi, uvicorn, httpx, websockets, psutil
from PIL import Image
from watchdog.observers import Observer
from mcp import ClientSession
if sys.version_info < (3, 11):
    import tomli
from fastapi.testclient import TestClient
from agent_orchestrator.dashboard import create_app
with tempfile.TemporaryDirectory(prefix='siling-update-startup-') as directory:
    root = Path(directory)
    config = root / 'dashboard.json'
    config.write_text('{}')
    os.environ['ORCH_DASHBOARD_CONFIG'] = str(config)
    app = create_app(root / 'outputs', token='update-smoke', projects_dir=root / 'projects',
                     ttyd_enabled=False, remote_nodes_enabled=False)
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/version').status_code == 401
        response = client.get('/api/version', headers={'Authorization': 'Bearer update-smoke'})
        assert response.status_code == 200
        assert response.json()['commit'] == sys.argv[1]
suite = unittest.defaultTestLoader.loadTestsFromNames([
    'tests.test_terminal_keys',
    'tests.test_terminal_reconnect.TerminalReconnectTests.test_inventory_failure_preserves_ttyd_and_shadow',
    'tests.test_terminal_reconnect.TerminalReconnectTests.test_browser_disconnect_releases_idle_upstream',
    'tests.test_terminal_reconnect.TerminalReconnectTests.test_upstream_failure_requests_automatic_browser_reconnect'])
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() and result.testsRun > 0 else 1)
'''
