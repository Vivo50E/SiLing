"""Explicit file links work outside workspace roots without granting directory access."""
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard


class ExternalFileLinkTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.projects = self.root / 'projects'
        self.project = self.projects / 'demo'
        self.project.mkdir(parents=True)
        self.external = self.root / 'outside'
        self.external.mkdir()
        self.file = self.external / 'application.yaml'
        self.content = 'apiVersion: v1\nspec:\n  project: default\n'
        self.file.write_text(self.content)
        self.run_dir = self.root / 'run'
        self.run_dir.mkdir()
        (self.run_dir / 'session.json').write_text('{}')
        self.stack.enter_context(patch.dict(os.environ, {
            'ORCH_PROJECTS_ROOT': str(self.projects), 'ORCH_LINKED_FOLDER_ROOTS': '',
            'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE': '0', 'ORCH_DASHBOARD_CONFIG': str(self.root / 'none'),
        }))
        self.stack.enter_context(patch.object(dashboard, '_lookup_run_light', side_effect=self.lookup))
        self.client = TestClient(dashboard.create_app(self.root, token='fixture', ttyd_enabled=False, remote_nodes_enabled=False))
        self.addCleanup(self.client.close)
        self.client.headers['Authorization'] = 'Bearer fixture'

    def lookup(self, outputs, run_id):
        return {'run_id':run_id, 'kind':'run', 'run_dir':str(self.run_dir),
                **(json.loads((self.run_dir / 'session.json').read_text()) if run_id == 'one' else {})}

    def link(self, path):
        return self.client.post('/api/sessions/one/folders', json={'path':str(path)})

    def test_external_file_links_preview_and_copy_raw_content(self):
        response = self.link(self.file)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['folder']['allowed'])
        artifact_id = json.loads((self.run_dir / 'session.json').read_text())['linked_folders'][0]['artifact']['id']
        for folder in (str(self.file), artifact_id):
            params = {'folder':folder, 'rel':''}
            preview = self.client.get('/api/sessions/one/folders/file', params=params)
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()['content'], self.content)
            raw = self.client.get('/api/sessions/one/folders/file/raw', params=params)
            self.assertEqual(raw.text, self.content)
            self.assertEqual(self.client.get('/api/sessions/two/folders/file', params=params).status_code, 400 if folder == str(self.file) else 404)
        self.assertFalse((self.external / 'TASK.json').exists())

    def test_external_directory_and_sibling_paths_remain_blocked(self):
        self.assertEqual(self.link(self.external).status_code, 400)
        self.assertEqual(self.link(self.file).status_code, 200)
        for rel in ('../other.yaml', 'other.yaml', '/etc/hosts'):
            result = self.client.get('/api/sessions/one/folders/file', params={'folder':str(self.file), 'rel':rel})
            self.assertEqual(result.status_code, 400)
        self.assertEqual(self.link(self.external / 'missing.yaml').status_code, 404)

    def test_directory_symlinks_do_not_bypass_roots_but_explicit_files_resolve(self):
        alias = self.project / 'alias.yaml'
        alias.symlink_to(self.file)
        with self.assertRaises(HTTPException):
            dashboard._resolve_folder_file(self.project, 'alias.yaml')
        response = self.link(alias)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['folder']['path'], str(self.file))
        folder_alias = self.project / 'external-dir'
        folder_alias.symlink_to(self.external, target_is_directory=True)
        self.assertEqual(self.link(folder_alias).status_code, 400)

    def test_auth_and_unlinked_file_checks_still_apply(self):
        self.assertEqual(self.client.get('/api/sessions/one/folders/file', params={'folder':str(self.file), 'rel':''}).status_code, 400)
        self.client.headers.pop('Authorization')
        self.client.cookies.clear()
        self.assertEqual(self.link(self.file).status_code, 401)
