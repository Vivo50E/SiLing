"""Artifact identity is separate from preview paths and survives legacy readers."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from agent_orchestrator import artifacts, cli, dashboard


class ArtifactTests(unittest.TestCase):
    def test_remote_identity_uses_source_not_cache_and_preserves_origin(self):
        one = {'path':'/cache/a.md', 'type':'file', 'label':'Report'}
        one['artifact'] = artifacts.metadata(one, {'run_id':'original'}, host='dev', source_path='/work/a.md', purpose='deliverable')
        moved = {**one, 'path':'/other/cache.md'}
        self.assertEqual(artifacts.metadata(moved, {'run_id':'resumed'}), one['artifact'])
        local = artifacts.metadata({'path':'/work/a.md','type':'file'})
        other = artifacts.metadata(one, host='other')
        self.assertNotEqual(local['id'], one['artifact']['id'])
        self.assertNotEqual(other['id'], one['artifact']['id'])
        for normalize in (cli._normalize_linked_folders, dashboard._normalize_linked_folders):
            self.assertEqual(normalize([one])[0]['artifact'], one['artifact'])

    def test_id_resolution_is_session_scoped_and_rechecks_access(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve()/'report.sql'
            path.write_text('select 1;')
            record = {'path':str(path),'label':'SQL','type':'file'}
            record['artifact'] = artifacts.metadata(record, {'run_id':'source'})
            run = {'linked_folders':[record]}
            with patch.object(dashboard, '_is_allowed_linked_folder', return_value=True):
                self.assertEqual(dashboard._resolve_linked_path_for_run(run, record['artifact']['id']), path)
                view = artifacts.describe(dashboard._linked_folder_summary(record), run)
                self.assertEqual(view['availability'], 'verified')
                self.assertEqual(view['preview_capability'], 'preview')
                with self.assertRaises(HTTPException):
                    dashboard._resolve_linked_path_for_run({'linked_folders':[]}, record['artifact']['id'])
                path.unlink()
                view = artifacts.describe(dashboard._linked_folder_summary(record), run)
                self.assertEqual(view['availability'], 'inaccessible')
                self.assertEqual(view['artifact_id'], record['artifact']['id'])
                with self.assertRaises(HTTPException):
                    dashboard._resolve_linked_path_for_run(run, record['artifact']['id'])

    def test_urls_are_not_claimed_reachable_and_legacy_records_stay_valid(self):
        view = artifacts.describe({'path':'https://example.test','type':'url','exists':True,'allowed':True}, {'run_id':'old'})
        self.assertEqual(view['availability'], 'candidate')
        self.assertEqual(view['artifact']['source_run_id'], 'old')
        self.assertEqual(view['artifact']['verified_at'], '')
        self.assertEqual(view['artifact']['purpose'], 'reference')

    def test_persist_and_cli_roundtrip_keeps_role_and_execution_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root/'report.txt';path.write_text('fixture')
            meta = root/'session.json';meta.write_text('{}')
            run = {'run_dir':str(root),'kind':'run','run_id':'origin','task':'task'}
            dashboard._persist_linked_path(run,path,'Report','file',artifact={'purpose':'deliverable','discovery':'claude-worker'})
            stored = json.loads(meta.read_text())
            original = stored['linked_folders'][0]['artifact']
            self.assertEqual(original['purpose'], 'deliverable')
            self.assertEqual(original['source_run_id'], 'origin')
            self.assertTrue(original['verified_at'])
            cli._add_linked_file(stored,path,'New label')
            self.assertEqual(stored['linked_folders'][0]['artifact'], original)
            self.assertEqual(len(stored['linked_folders']), 1)

    def test_legacy_resume_copy_attributes_artifact_to_original_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            child = root/'child';child.mkdir();(child/'session.json').write_text('{}')
            report = root/'report.md';report.write_text('Fixture')
            source = {'run_id':'original','linked_folders':[{'path':str(report),'type':'file','label':'Report'}]}
            result = dashboard._copy_linked_folders_to_spawned_run(root, source, {'run_dir':str(child)})
            self.assertEqual(result['copied'], 1)
            stored = json.loads((child/'session.json').read_text())['linked_folders'][0]
            self.assertEqual(artifacts.metadata(stored, {'run_id':'child'})['execution_id'], 'original')
