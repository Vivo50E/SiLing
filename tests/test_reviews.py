import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent_orchestrator import reviews, dashboard


class ReviewTests(unittest.TestCase):
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
        self.assertIn('github.com/base/r',calls[-1])
        self.assertIn('feature/test',calls[-1])

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
