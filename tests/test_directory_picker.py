import asyncio
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from agent_orchestrator import dashboard, directory_picker


class DirectoryPickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_path_and_cancellation_use_fixed_script_and_literal_argument(self):
        with tempfile.TemporaryDirectory(prefix='picker test ') as temporary:
            root = Path(temporary).resolve()
            target = root / 'quotes " and $()'
            target.mkdir()
            for raw, expected in [(str(target).encode()+b'/\n', str(target)), (b'\n', None)]:
                process = Mock(returncode=0, communicate=AsyncMock(return_value=(raw,None)))
                with patch.object(directory_picker.asyncio,'create_subprocess_exec',AsyncMock(return_value=process)) as spawn:
                    result = await directory_picker.choose_directory(str(target))
                    self.assertEqual(result, expected)
                    self.assertEqual(spawn.call_args.args,('/usr/bin/osascript','-e',directory_picker._SCRIPT,str(target)))
                    self.assertNotIn(str(target),directory_picker._SCRIPT)

    async def test_busy_invalid_paths_and_timeout_never_leak_or_leave_process_running(self):
        directory_picker._BUSY.acquire()
        try:
            with self.assertRaises(HTTPException) as error:
                await directory_picker.choose_directory('')
            self.assertEqual(error.exception.status_code,409)
        finally:
            directory_picker._BUSY.release()
        for value in (None, [], 'x\ncommand', 'x'*4097):
            with patch.object(directory_picker.asyncio,'create_subprocess_exec',AsyncMock()) as spawn:
                with self.assertRaises(HTTPException):
                    await directory_picker.choose_directory(value)
                spawn.assert_not_called()
        for failure in (asyncio.TimeoutError(), asyncio.CancelledError()):
            process = Mock(returncode=None, communicate=AsyncMock(side_effect=failure), wait=AsyncMock())
            with patch.object(directory_picker.asyncio,'create_subprocess_exec',AsyncMock(return_value=process)):
                with self.assertRaises((HTTPException, asyncio.CancelledError)):
                    await directory_picker.choose_directory('')
                process.kill.assert_called_once(); process.wait.assert_awaited_once()
                self.assertFalse(directory_picker._BUSY.locked())
        for raw in (b'not-absolute\n', b'\xff', b'/missing/picker-fixture\n'):
            process = Mock(returncode=0, communicate=AsyncMock(return_value=(raw,None)))
            with patch.object(directory_picker.asyncio,'create_subprocess_exec',AsyncMock(return_value=process)):
                with self.assertRaises(HTTPException):
                    await directory_picker.choose_directory('')
                self.assertFalse(directory_picker._BUSY.locked())


class DirectoryPickerAPITests(unittest.TestCase):
    def test_requires_auth_local_peer_explicit_intent_and_same_origin(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ',{'ORCH_ACTIVE_SNAPSHOT_AUTOSAVE':'0'}))
            stack.enter_context(patch('agent_orchestrator.browser_open.sys.platform','darwin'))
            picked = stack.enter_context(patch.object(dashboard,'choose_directory',AsyncMock(return_value='/fixture/project with spaces')))
            app = dashboard.create_app(Path(temporary),token='fixture',ttyd_enabled=False,remote_nodes_enabled=False)
            client = stack.enter_context(TestClient(app,client=('127.0.0.1',1234)))
            path = '/api/directories/pick'
            headers = {'Authorization':'Bearer fixture','X-SiLing-Directory-Pick':'user-click'}
            self.assertEqual(client.post(path,json={'cwd':''}).status_code,401)
            self.assertTrue(client.get('/api/config',headers=headers).json()['directory_picker_available'])
            for extra in ({'Origin':'https://evil.invalid'}, {'Sec-Fetch-Site':'cross-site'}, {'X-Forwarded-For':'127.0.0.1'}):
                self.assertEqual(client.post(path,json={'cwd':''},headers={**headers,**extra}).status_code,403)
            self.assertEqual(client.post(path,json={'cwd':''},headers={'Authorization':'Bearer fixture'}).status_code,403)
            for body in ([], {}, {'cwd':'','node_id':'remote'}):
                self.assertEqual(client.post(path,json=body,headers=headers).status_code,400)
            picked.assert_not_called()
            result = client.post(path,json={'cwd':'~/project'},headers={**headers,'Origin':'http://testserver'})
            self.assertEqual(result.json(),{'ok':True,'cancelled':False,'path':'/fixture/project with spaces'})
            self.assertEqual(result.headers['cache-control'],'no-store')
            picked.assert_awaited_once_with('~/project')
            picked.return_value = None
            self.assertTrue(client.post(path,json={'cwd':''},headers=headers).json()['cancelled'])
            with patch.object(dashboard,'system_browser_available',return_value=False):
                self.assertEqual(client.post(path,json={'cwd':''},headers=headers).status_code,403)
