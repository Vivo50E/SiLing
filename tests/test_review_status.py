from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, reviews


class ReviewStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hosts = {'gh': {'github.com'}, 'glab': {'gitlab.example'}}
        for stub in [patch.object(reviews, 'provider_hosts', return_value=self.hosts),
                     patch.object(reviews, 'branch_reviews', return_value=([], 'feature', ''))]:
            stub.start(); self.addCleanup(stub.stop)

    @contextmanager
    def clock(self, *, now=None, ticks=None):
        # Keep the real time module available to unrelated Dashboard workers.
        with patch.object(reviews, 'time', wraps=time) as clock:
            if now is not None:
                clock.time.return_value = now
            if ticks is not None:
                clock.monotonic.side_effect = ticks
            yield

    def item(self, number=10, kind='MR'):
        url = (f'https://gitlab.example/group/sub/repo/-/merge_requests/{number}' if kind == 'MR'
               else f'https://github.com/org/repo/pull/{number}')
        return dict(reviews.review_url(url), source='output')

    def response(self, args, cwd, timeout=3):
        item = self.item(int(args[3]), 'PR' if args[0] == 'gh' else 'MR')
        return json.dumps({'url':item['url'], 'web_url':item['url'], 'title':'Provider title', 'state':'merged'})

    def test_fixed_cli_commands_query_exact_github_and_nested_gitlab_review(self):
        for kind in ['PR', 'MR']:
            with self.subTest(kind=kind), patch.object(reviews, '_run', side_effect=self.response) as run:
                result = reviews.lookup_review(self.item(kind=kind), None, self.hosts)
                self.assertEqual(result['state'], 'merged')
                self.assertEqual(result['status_error'], '')
                args = run.call_args.args[0]
                self.assertEqual(args[:4], ['gh' if kind == 'PR' else 'glab', 'pr' if kind == 'PR' else 'mr', 'view', '10'])
                self.assertIn('github.com/org/repo' if kind == 'PR' else 'https://gitlab.example/group/sub/repo', args)

    def test_untrusted_hosts_insecure_urls_and_unsafe_projects_never_run_cli(self):
        for url in ['https://github.evil.invalid/o/r/pull/1', 'http://github.com/o/r/pull/1',
                    'https://github.com/../r/pull/1', 'https://token@github.com/o/r/pull/1']:
            with self.subTest(url=url), patch.object(reviews, '_run') as run:
                result = reviews.lookup_review({'url':url}, None, self.hosts)
                self.assertIn(result['status_error'], {'unsupported', 'host_unconfigured'})
                run.assert_not_called()

    def test_malformed_wrong_identity_and_errors_do_not_expose_provider_output(self):
        cases = [('[]', 'unavailable'), ('{"url":"https://github.com/o/r/pull/2","state":"open"}', 'unavailable'),
                 ('fixture-private-output', 'unavailable'), (FileNotFoundError(), 'cli_missing'),
                 (subprocess.TimeoutExpired(['fixture'],3), 'timeout'), (ValueError('fixture-private-output'), 'unavailable')]
        for value, error in cases:
            with self.subTest(error=error), patch.object(reviews, '_run', **({'side_effect':value} if isinstance(value,Exception) else {'return_value':value})):
                result = reviews.lookup_review(self.item(), None, self.hosts)
                self.assertEqual(result['status_error'], error)
                self.assertNotIn('state', result)
                self.assertNotIn('fixture-private-output', json.dumps(result))

    def test_drafts_only_override_open_state(self):
        for raw, expected in [('opened','draft'), ('merged','merged'), ('closed','closed')]:
            row = {'web_url':self.item()['url'], 'state':raw, 'draft':True}
            with self.subTest(state=raw), patch.object(reviews, '_run', return_value=json.dumps(row)):
                self.assertEqual(reviews.lookup_review(self.item(), None, self.hosts)['state'], expected)

    def test_output_and_manual_links_hydrate_cache_and_refresh_without_branch_match(self):
        output = self.item()['url']
        manual = self.item(11, 'PR')['url']
        run = {'linked_folders':[{'path':manual, 'label':'Custom label'}]}
        with patch.object(reviews, '_run', side_effect=self.response) as execute, self.clock(now=100):
            first = reviews.discover(run, output, self.root, lookup=False, status_lookup=True)
            self.assertEqual({item['state'] for item in first['items']}, {'merged'})
            self.assertEqual(execute.call_count, 2)
            cached = reviews.discover(run, '', self.root, lookup=False, status_lookup=True)
            self.assertEqual(execute.call_count, 2, 'Opening again uses the one-minute status cache')
            self.assertEqual(next(item['title'] for item in cached['items'] if item['url']==manual), 'Custom label')
            def opened(args, cwd, timeout=3):
                row = json.loads(self.response(args,cwd,timeout)); row['state']='opened';return json.dumps(row)
            execute.side_effect = opened
            refreshed = reviews.discover(run, '', self.root, lookup=False, status_lookup=True, force_status=True)
            self.assertEqual({item['state'] for item in refreshed['items']}, {'open'})
            self.assertEqual(execute.call_count, 4)
            execute.reset_mock()
            counts = reviews.discover(run, '', self.root, lookup=False)
            execute.assert_not_called()
            self.assertEqual({item['state'] for item in counts['items']}, {'open'})
            removed = reviews.discover({}, '', self.root, lookup=False)
            self.assertEqual([item['url'] for item in removed['items']], [output], 'Cached manual status does not create an association')

    def test_refresh_failure_retains_known_state_timestamp_and_reports_error(self):
        url = self.item()['url']
        with patch.object(reviews, '_run', side_effect=self.response), self.clock(now=100):
            reviews.discover({}, url, self.root, lookup=False, status_lookup=True)
        with patch.object(reviews, '_run', side_effect=ValueError('fixture-private-output')), self.clock(now=110):
            result = reviews.discover({}, '', self.root, lookup=False, status_lookup=True, force_status=True)
        self.assertEqual(result['items'][0]['state'], 'merged')
        self.assertEqual(result['items'][0]['status_checked_at'], 100)
        self.assertEqual(result['items'][0]['status_error'], 'unavailable')
        self.assertEqual(result['status_failed'], 1)
        self.assertNotIn('fixture-private-output', json.dumps(result))
        self.assertEqual(reviews.discover({}, '', self.root, lookup=False)['items'][0]['state'], 'merged')

    def test_terminal_route_resolves_urls_and_badge_requests_only_read_cache(self):
        (self.root/'pane.log').write_text(self.item()['url'])
        outputs=self.root/'outputs'
        run={'agent':'terminal','run_dir':str(self.root),'log_file':'pane.log'}
        original=dashboard._lookup_run_light
        app=dashboard.create_app(outputs,token='fixture-auth',ttyd_enabled=False,remote_nodes_enabled=False)
        with TestClient(app) as client, patch.object(dashboard,'_lookup_run_light',side_effect=lambda directory,run_id:
                run if directory==outputs and run_id=='fixture' else original(directory,run_id)), \
                patch.object(reviews,'branch_reviews') as branch, patch.object(reviews,'_run',side_effect=self.response) as execute:
            url='/api/sessions/fixture/reviews';headers={'Authorization':'Bearer fixture-auth'}
            self.assertEqual(client.get(url).status_code,401)
            self.assertEqual(client.get(url+'?branch=false',headers=headers).json()['items'][0]['state'],'unknown')
            execute.assert_not_called()
            self.assertEqual(client.get(url,headers=headers).json()['items'][0]['state'],'merged')
            self.assertEqual(execute.call_count,1)
            self.assertEqual(client.get(url+'?branch=false',headers=headers).json()['items'][0]['state'],'merged')
            self.assertEqual(execute.call_count,1)
            client.get(url+'?branch=false&refresh=true',headers=headers)
            self.assertEqual(execute.call_count,2)
            branch.assert_not_called()

    def test_bounded_batches_continue_with_oldest_unchecked_link(self):
        text = ' '.join(self.item(i)['url'] for i in [1,2])
        with patch.object(reviews, 'STATUS_LIMIT', 1), patch.object(reviews, '_run', side_effect=self.response) as run:
            first = reviews.discover({}, text, self.root, lookup=False, status_lookup=True, force_status=True)
            self.assertEqual(first['status_pending'], 1)
            second = reviews.discover({}, '', self.root, lookup=False, status_lookup=True, force_status=True)
            self.assertEqual(second['status_pending'], 0, 'Recent completed batches do not create an endless refresh prompt')
            self.assertEqual([call.args[0][3] for call in run.call_args_list], ['1','2'])
            self.assertEqual({item['state'] for item in second['items']}, {'merged'})

    def test_workers_and_time_budget_are_bounded(self):
        lock = threading.Lock(); active = 0; peak = 0
        def query(args,cwd,timeout=3):
            nonlocal active, peak
            with lock:active += 1;peak=max(peak,active)
            time.sleep(.02)
            with lock:active -= 1
            return self.response(args,cwd,timeout)
        with patch.object(reviews, '_run', side_effect=query):
            updates, pending = reviews.refresh_statuses([self.item(i) for i in range(1,9)], None)
        self.assertEqual(len(updates),8);self.assertEqual(pending,0)
        self.assertGreater(peak,1);self.assertLessEqual(peak,4)
        with self.clock(ticks=[0,1,13]), patch.object(reviews, '_run', side_effect=self.response) as run:
            time.monotonic()  # A background clock read must not consume the query's budget fixture.
            updates,pending = reviews.refresh_statuses([self.item(i) for i in range(1,9)], None)
        self.assertEqual(run.call_count,4);self.assertEqual(pending,4)

    def test_slower_old_request_cannot_replace_newer_state_or_hold_index_lock(self):
        started = threading.Event(); release = threading.Event(); counter = 0
        def query(item, cwd, hosts, timeout=3):
            nonlocal counter
            counter += 1
            if counter == 1:
                started.set()
                if not release.wait(3):
                    raise AssertionError('Index lock blocked a newer refresh')
                return {'state':'open','status_attempted_at':100,'status_checked_at':100,'status_error':''}
            return {'state':'merged','status_attempted_at':200,'status_checked_at':200,'status_error':''}
        with patch.object(reviews, 'lookup_review', side_effect=query), ThreadPoolExecutor(max_workers=1) as worker:
            older = worker.submit(reviews.discover, {}, self.item()['url'], self.root,
                                  lookup=False, status_lookup=True, force_status=True)
            try:
                self.assertTrue(started.wait(2))
                newer = reviews.discover({}, '', self.root, lookup=False, status_lookup=True, force_status=True)
                self.assertEqual(newer['items'][0]['state'], 'merged')
            finally:
                release.set()
            self.assertEqual(older.result(2)['items'][0]['state'], 'merged')
        self.assertEqual(reviews.discover({}, '', self.root, lookup=False)['items'][0]['status_checked_at'], 200)


class ProviderHostTests(unittest.TestCase):
    def test_only_cli_host_keys_and_explicit_host_environment_are_trusted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); gh=root/'gh';glab=root/'glab';gh.mkdir();glab.mkdir()
            (gh/'hosts.yml').write_text('github.enterprise.example:\n  oauth_token: fixture-secret\n')
            (glab/'config.yml').write_text('hosts:\n  gitlab.enterprise.example:\n    token: fixture-secret\n')
            with patch.dict(os.environ, {'GH_CONFIG_DIR':str(gh),'GLAB_CONFIG_DIR':str(glab),'GH_HOST':'','GITLAB_HOST':'gitlab.env.example'}):
                hosts=reviews.provider_hosts()
            self.assertEqual(hosts['gh'], {'github.com','github.enterprise.example'})
            self.assertEqual(hosts['glab'], {'gitlab.com','gitlab.enterprise.example','gitlab.env.example'})
            self.assertNotIn('fixture-secret',repr(hosts))
