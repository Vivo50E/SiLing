import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent_orchestrator import reviews, dashboard


class ReviewTests(unittest.TestCase):
    def fixture_lookup(self, root, run):
        original = dashboard._lookup_run_light
        return patch.object(dashboard, '_lookup_run_light', side_effect=lambda outputs, run_id:
                            run if outputs == root/'outputs' and run_id == 'fixture'
                            else original(outputs, run_id))

    def test_urls_normalize_suffixes_without_accepting_credentials_or_scripts(self):
        pr = reviews.review_url('https://github.com/org/repo/pull/12/files?tab=x#diff')
        self.assertEqual(pr['url'], 'https://github.com/org/repo/pull/12')
        mr = reviews.review_url('https://gitlab.example/group/sub/repo/-/merge_requests/5/diffs')
        self.assertEqual(mr['kind'], 'MR')
        self.assertEqual(mr['project'], 'group/sub/repo')
        for bad in ['javascript:alert(1)', 'https://token@github.com/o/r/pull/1',
                    'https://github.com/o/r/issues/1', 'https://github.com/o/r/pull/0',
                    'https://github.com/o/r/pull/1\nmore']:
            self.assertIsNone(reviews.review_url(bad), bad)

    def test_collect_deduplicates_and_labels_evidence(self):
        url = 'https://github.com/o/r/pull/1'
        run = {'linked_folders': [{'path':url,'label':'Linked title'}]}
        result = reviews.collect(run, f'Link ({url}/files) https://gitlab.example/g/r/-/merge_requests/8', lookup=False)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['source'], 'linked')
        self.assertEqual(result['items'][0]['title'], 'Linked title')
        self.assertEqual(result['items'][1]['state'], 'unknown')
        self.assertEqual(reviews.collect({}, url+' '*262144, lookup=False)['items'], [])

    def test_github_upstream_branch_lookup_filters_other_forks(self):
        calls=[]
        def execute(args, cwd, timeout=3):
            calls.append(args)
            if args[0]=='gh':
                return json.dumps([{'url':f'https://github.com/base/r/pull/{i}', 'title':'Change',
                                    'state':'OPEN','headRepositoryOwner':{'login':owner}}
                                   for i,owner in [(1,'mine'),(2,'someone-else')]])
            return {'HEAD':'feature/test','origin':'git@github.com:mine/r.git',
                    'upstream':'https://github.com/base/r.git'}[args[-1]]
        with patch.object(reviews, '_run', side_effect=execute):
            rows, branch, warning=reviews.branch_reviews('/fixture')
        self.assertEqual([r['number'] for r in rows],[1])
        self.assertEqual(branch,'feature/test')
        self.assertEqual(warning,'')
        self.assertEqual([args[args.index('--repo')+1] for args in calls if args[0]=='gh'],
                         ['github.com/base/r','github.com/mine/r'])
        self.assertIn('feature/test',calls[-1])

    def test_fork_origin_results_survive_upstream_lookup_failure(self):
        def execute(args, cwd, timeout=3):
            if args[0] == 'gh':
                if 'github.com/base/r' in args:
                    raise ValueError('upstream unavailable')
                return json.dumps([{'url':'https://github.com/mine/r/pull/7',
                                    'headRepositoryOwner':{'login':'mine'}}])
            return {'HEAD':'feature','origin':'git@github.com:mine/r.git',
                    'upstream':'git@github.com:base/r.git'}[args[-1]]
        with patch.object(reviews, '_run', side_effect=execute):
            rows, _, warning = reviews.branch_reviews('/fixture')
        self.assertEqual([row['number'] for row in rows], [7])
        self.assertTrue(warning)

    def test_history_cursor_overlap_rotation_and_session_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root/'pane.log'
            url = 'https://github.com/o/r/pull/9'
            log.write_text('x'*100 + ' ' + url + ' ' + 'x'*600)
            run = {'run_dir':temp, 'log_file':'pane.log'}
            with patch.object(reviews, 'SCAN_BYTES', 128):
                result = reviews.discover(run, '', root/'a', lookup=False)
                self.assertTrue(result['history_pending'])
                for _ in range(12):
                    result = reviews.discover(run, '', root/'a', lookup=False)
                    if not result['history_pending']:
                        break
            self.assertEqual([item['url'] for item in result['items']], [url])
            self.assertFalse(result['history_pending'])
            log.unlink()
            log.write_text('https://gitlab.example/g/r/-/merge_requests/6')
            result = reviews.discover(run, '', root/'a', lookup=False)
            self.assertEqual(len(result['items']), 2)
            self.assertEqual(reviews.discover({}, '', root/'b', lookup=False)['items'], [])

    def test_removed_manual_link_is_not_kept_as_an_automatic_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            run = {'linked_folders':[{'path':'https://github.com/o/r/pull/4'}]}
            self.assertEqual(len(reviews.discover(run, '', temp, lookup=False)['items']), 1)
            self.assertEqual(reviews.discover({}, '', temp, lookup=False)['items'], [])

    def test_manual_links_keep_observed_status_and_custom_label_on_reload(self):
        url = 'https://github.com/o/r/pull/4'
        run = {'cwd':'/fixture', 'linked_folders':[{'path':url, 'label':'Custom label'}]}
        for status in ['open', 'merged']:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temp:
                item = dict(reviews.review_url(url), source='branch', state=status, title='Provider title')
                with patch.object(reviews, 'branch_reviews', return_value=([item], 'feature', '')):
                    reviews.discover(run, '', temp)
                with patch.object(reviews, 'branch_reviews') as branch:
                    result = reviews.discover(run, '', temp, lookup=False)['items']
                    branch.assert_not_called()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['state'], status)
                self.assertEqual(result[0]['title'], 'Custom label')
                self.assertEqual(result[0]['source'], 'linked')

    def test_branch_results_remain_available_to_initial_counts_after_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = {'agent':'codex','cwd':temp}
            item = dict(reviews.review_url('https://github.com/o/r/pull/3'), source='branch')
            app = dashboard.create_app(root/'outputs',token='fixture',ttyd_enabled=False,remote_nodes_enabled=False)
            with TestClient(app) as client, self.fixture_lookup(root, run), \
                    patch.object(reviews,'branch_reviews',return_value=([item],'feature','')) as branch:
                path = '/api/sessions/fixture/reviews'
                headers = {'Authorization':'Bearer fixture'}
                self.assertEqual(len(client.get(path,headers=headers).json()['items']), 1)
                branch.reset_mock()
                self.assertEqual(len(client.get(path+'?branch=false',headers=headers).json()['items']), 1)
                branch.assert_not_called()

    def test_route_retains_discoveries_across_refresh_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root/'pane.log'
            early = 'https://github.com/o/r/pull/1'
            recent = 'https://github.com/o/r/pull/2'
            branch_url = 'https://github.com/o/r/pull/3'
            log.write_text(early+'\n'+' '*300000+recent)
            run = {'agent':'codex','cwd':temp,'run_dir':temp,'log_file':'pane.log'}
            headers = {'Authorization':'Bearer fixture'}
            def app():
                return dashboard.create_app(root/'outputs',token='fixture',ttyd_enabled=False,remote_nodes_enabled=False)
            with self.fixture_lookup(root, run), \
                    patch.object(reviews,'branch_reviews',return_value=([dict(reviews.review_url(branch_url),source='branch',title='Saved title',state='open')],'feature','')) as branch:
                with TestClient(app()) as client:
                    path = '/api/sessions/fixture/reviews'
                    result = client.get(path,headers=headers).json()
                    self.assertEqual({row['url'] for row in result['items']}, {early,recent,branch_url})
                    log.write_text('no links remain in the live output')
                    branch.return_value = ([], 'another-branch', 'Lookup failed')
                    self.assertEqual(len(client.get(path,headers=headers).json()['items']), 3)
                    branch.reset_mock()
                    self.assertEqual(len(client.get(path+'?branch=false',headers=headers).json()['items']), 3)
                    branch.assert_not_called()
                with TestClient(app()) as client:
                    restored = client.get(path+'?branch=false',headers=headers).json()['items']
                    self.assertEqual(len(restored), 3)
                    self.assertEqual(next(row for row in restored if row['url']==branch_url)['title'], 'Saved title')

    def test_gitlab_nested_project_and_failure_keep_linked_results(self):
        def execute(args,cwd,timeout=3):
            if args[0]=='glab':
                self.assertIn('https://gitlab.example/g/sub/r',args)
                return json.dumps([{'web_url':'https://gitlab.example/g/sub/r/-/merge_requests/2','state':'merged','title':'Merged fixture'}])
            if args[-1]=='upstream': raise ValueError()
            return 'feature' if args[-1]=='HEAD' else 'git@gitlab.example:g/sub/r.git'
        with patch.object(reviews,'_run',side_effect=execute):
            self.assertEqual(reviews.branch_reviews('/fixture')[0][0]['state'],'merged')
        with patch.object(reviews,'_run',side_effect=FileNotFoundError):
            result=reviews.collect({'cwd':'/fixture','linked_folders':[{'path':'https://github.com/o/r/pull/1'}]})
        self.assertTrue(result['warning'])
        self.assertEqual(len(result['items']),1)

    def test_authenticated_route_reads_bounded_output_and_skips_shell_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'pane.log').write_text('x'*300000+' https://github.com/o/r/pull/9')
            run={'agent':'terminal','cwd':temp,'run_dir':temp,'log_file':'pane.log','tmux_session':'fixture'}
            app=dashboard.create_app(root/'outputs',token='fixture',ttyd_enabled=False,remote_nodes_enabled=False)
            with TestClient(app) as client, patch.object(dashboard,'_lookup_run_light',return_value=run), \
                    patch.object(dashboard,'tmux_alive',return_value=True), \
                    patch.object(dashboard,'tmux_capture_lines',return_value='https://gitlab.example/g/r/-/merge_requests/2'), \
                    patch.object(reviews,'branch_reviews') as branch:
                url='/api/sessions/fixture/reviews'
                self.assertEqual(client.get(url).status_code,401)
                result=client.get(url,headers={'Authorization':'Bearer fixture'})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(len(result.json()['items']),2)
                branch.assert_not_called()
