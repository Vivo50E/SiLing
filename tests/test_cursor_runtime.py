import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent_orchestrator import cursor_runtime


class CursorRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required')
    def test_process_local_menu_selection_survives_restart_and_other_panes(self):
        subprocess.run(['node', 'tests/cursor_model_state.cjs'],
                       cwd=Path(__file__).resolve().parents[1], check=True,
                       capture_output=True, text=True, timeout=15)

    def test_only_matching_conversation_can_restore_model(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / cursor_runtime.MODEL_STATE
            path.write_text(json.dumps({'version': 1, 'conversation_id': 'one',
                'fields': {'model': {'modelId': 'sonnet'}, 'authInfo': 'private'}}))
            self.assertIsNone(cursor_runtime.saved_model(temp, 'two'))
            self.assertNotIn('authInfo', cursor_runtime.saved_model(temp, 'one')['fields'])
            path.write_text('{broken')
            self.assertIsNone(cursor_runtime.saved_model(temp, 'one'))

    def test_auth_preflight_never_initiates_login_and_does_not_expose_output(self):
        with patch.dict(os.environ, {'CURSOR_API_KEY': '', 'CURSOR_AUTH_TOKEN': ''}):
            for output, code, ok in [('{"isAuthenticated":true}',0,True),
                                      ('{"isAuthenticated":false}',0,False),
                                      ('private-error-text',1,False)]:
                with self.subTest(output=output), patch.object(cursor_runtime.subprocess, 'run',
                        return_value=subprocess.CompletedProcess([],code,output,'private-stderr')) as run:
                    if ok:
                        cursor_runtime.check_auth('/fixture/agent','/fixture')
                    else:
                        with self.assertRaises(RuntimeError) as error:
                            cursor_runtime.check_auth('/fixture/agent','/fixture')
                        self.assertNotIn('private',str(error.exception))
                    self.assertEqual(run.call_args.args[0], ['/fixture/agent','status','--format','json'])
                    self.assertEqual(run.call_args.kwargs['stdin'],subprocess.DEVNULL)
                    self.assertEqual(run.call_args.kwargs['timeout'],15)

    def test_auth_timeout_keeps_old_agent(self):
        with patch.dict(os.environ, {'CURSOR_API_KEY': '', 'CURSOR_AUTH_TOKEN': ''}), patch.object(
                cursor_runtime.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture',15)):
            with self.assertRaisesRegex(RuntimeError,'agent was not stopped'):
                cursor_runtime.check_auth('/fixture/agent','/fixture')
