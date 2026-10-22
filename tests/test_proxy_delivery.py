"""Live mode changes must not interrupt work, submit drafts or replay input."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_orchestrator import proxy_delivery, dashboard


class ProxyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'session.json'
        self.path.write_text(json.dumps({'proxy_mode_applied':'local'}))
        self.row = {'kind':'run', 'run_dir':self.tmp.name, 'run_id':'one::agent',
                    'agent':'claude', 'alive':True, 'busy':False, 'tmux_session':'fixture'}
        self.probe = Mock(return_value='stable empty editor')
        self.send = Mock(return_value=True)
        self.refresh = Mock()
        self.service = proxy_delivery.ProxyDelivery(lambda:[self.row], self.probe, self.send, self.refresh)
        self.clock = patch.object(proxy_delivery.time, 'monotonic', return_value=10)
        self.now = self.clock.start(); self.addCleanup(self.clock.stop)
        self.save('devin')

    def save(self, mode):
        self.row.update(proxy_delivery.save(self.row, mode))

    def stored(self):
        return json.loads(self.path.read_text())

    def tick(self):
        self.service.tick([self.row])
        self.now.return_value += 3

    def test_busy_then_idle_sends_once_without_restart(self):
        self.row['busy'] = True
        self.tick(); self.tick(); self.send.assert_not_called()
        self.row['busy'] = False
        self.tick(); self.send.assert_not_called()
        self.tick(); self.tick()
        self.send.assert_called_once()
        self.assertIn('Remote proxy mode: devin', self.send.call_args.args[1])
        self.assertEqual(self.stored()['proxy_delivery_status'], 'sent')
        self.assertEqual(self.stored()['proxy_mode_applied'], 'devin')
        self.save('devin'); self.tick(); self.tick()
        self.send.assert_called_once()

    def test_empty_editor_and_stable_screen_required(self):
        self.probe.return_value = ''
        self.tick(); self.tick(); self.send.assert_not_called()
        self.probe.return_value = 'empty'
        self.tick()
        self.probe.return_value = 'changed'
        self.tick(); self.send.assert_not_called()
        self.tick(); self.send.assert_called_once()

    def test_latest_choice_supersedes_unsent_mode(self):
        self.tick(); self.save('cmux-cloud'); self.tick(); self.tick()
        self.send.assert_called_once()
        self.assertIn('Remote proxy mode: cmux-cloud', self.send.call_args.args[1])

    def test_change_during_send_is_not_lost(self):
        def send(*args):
            self.save('local')
            return True
        self.send.side_effect = send
        self.tick(); self.tick()
        self.assertEqual(self.stored()['proxy_mode'], 'local')
        self.assertEqual(self.stored()['proxy_mode_applied'], 'devin')
        self.assertEqual(self.stored()['proxy_delivery_status'], 'queued')
        self.send.side_effect = None
        self.tick(); self.tick()
        self.assertEqual(self.stored()['proxy_mode_applied'], 'local')
        self.assertIn('OFF', self.send.call_args.args[1])

    def test_uncertain_or_crashed_delivery_is_never_replayed(self):
        self.send.return_value = False
        self.tick(); self.tick()
        self.assertEqual(self.stored()['proxy_delivery_status'], 'uncertain')
        self.save('devin')
        self.tick(); self.tick(); self.send.assert_called_once()
        data = self.stored(); data['proxy_delivery_status'] = 'sending'
        self.path.write_text(json.dumps(data))
        recovered = proxy_delivery.ProxyDelivery(lambda:[self.row], self.probe, self.send, self.refresh)
        recovered.tick([self.row]); recovered.tick([self.row])
        self.send.assert_called_once()

    def test_not_ready_after_claim_returns_to_queue_without_input(self):
        self.tick()
        self.probe.side_effect = ['stable empty editor', '']
        self.tick()
        self.assertEqual(self.stored()['proxy_delivery_status'], 'queued')
        self.send.assert_not_called()

    def test_stopped_remote_exited_and_unknown_activity_never_send(self):
        for values in ({'alive':False}, {'remote':True}, {'agent_exited':True},
                       {'busy':None}, {'background_active':True}, {'agent':'terminal'}):
            with self.subTest(values=values):
                row = {**self.row, **values}
                self.service.tick([row]); self.now.return_value += 3; self.service.tick([row])
        self.send.assert_not_called()


class EmptyEditorTests(unittest.TestCase):
    def test_fresh_probe_refuses_shell_copy_mode_and_running_footer(self):
        import subprocess
        row = {'tmux_session':'probe-fixture'}
        for info, screen in [
            ('%9\t2\t1\t0\t0\tbash', 'Output\n❯ \n bypass permissions mode on'),
            ('%9\t2\t1\t1\t0\tnode', 'Output\n❯ \n bypass permissions mode on'),
            ('%9\t2\t1\t0\t0\tnode', 'Output\n→ \n/ for commands · ctrl+c to stop'),
        ]:
            replies = [subprocess.CompletedProcess([],0,info,''),
                       subprocess.CompletedProcess([],0,screen,'')]
            with self.subTest(info=info), patch.object(dashboard.subprocess,'run',side_effect=replies):
                self.assertEqual(dashboard._proxy_ready_screen(row),'')

    def test_empty_and_dim_placeholder_but_not_typed_or_multiline_draft(self):
        for screen, x, ready in [
            ('Output\n❯ \n  bypass permissions mode on',2,True),
            ('Output\n› \x1b[2mAsk Codex to do anything\x1b[0m\n? for shortcuts',2,True),
            ('Output\n\x1b[2m→ Add a follow-up\x1b[0m\n/ for commands',2,True),
            ('Output\n→ Add a follow-up\n/ for commands',2,False),
            ('Output\n› Ask Codex to do anything\n? for shortcuts',2,False),
            ('Output\n❯ my draft\n  bypass permissions mode on',10,False),
            ('Output\n❯ \n  multiline draft\n  bypass permissions mode on',2,False),
            ('Output\n❯ 1. Yes\n  bypass permissions mode on',2,False),
        ]:
            with self.subTest(screen=screen):
                self.assertEqual(proxy_delivery.empty_editor(screen,x,1),ready)

    def test_input_race_after_paste_never_sends_enter_or_retries(self):
        row={'_proxy_pane':'%999','tmux_session':'proxy-fixture','_proxy_input_stamp':0}
        def send(*args, **kwargs):
            self.assertEqual(kwargs['retries'],0)
            dashboard._PROXY_LAST_INPUT['proxy-fixture'] = 1
            return True,''
        try:
            with patch.object(dashboard,'_tmux_send_keys',side_effect=send) as transport, patch.object(dashboard.time,'sleep'):
                self.assertFalse(dashboard._send_proxy_instruction(row,'test rule'))
                transport.assert_called_once()
        finally:
            dashboard._PROXY_LAST_INPUT.pop('proxy-fixture',None)


class LiveProxyTmuxTests(unittest.TestCase):
    def test_owned_terminal_keeps_draft_then_receives_one_bracketed_message(self):
        import os
        import shlex
        import shutil
        import subprocess
        import time
        tmux, node = shutil.which('tmux'), shutil.which('node')
        if not tmux or not node:
            self.skipTest('tmux and Node.js required')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            socket, output = root/'socket', root/'message.json'
            script = root/'agent.cjs'
            script.write_text('''const fs=require('fs');process.stdin.setRawMode(true);
let text='keep draft';
function render(){process.stdout.write('\\x1b[2J\\x1b[HFixture agent\\r\\n❯ '+text+'\\r\\n  bypass permissions mode on\\x1b[2;'+(3+text.length)+'H\\x1b[?2004h');}
render();process.stdin.on('data',data=>{const value=data.toString();if(value==='\\x15'){text='';render();return;}text+=value;if(text.includes('\\x1b[201~')&&text.endsWith('\\r')){fs.writeFileSync(process.argv[2],JSON.stringify(text));text='';render();}});
''')
            run = subprocess.run
            def owned(args, **kwargs):
                if args[0] == 'tmux':
                    args = [tmux,'-S',str(socket),*args[1:]]
                return run(args, **kwargs)
            owned(['tmux','-f','/dev/null','new-session','-d','-s','proxy-test','-x','100','-y','20',
                   'exec '+shlex.join([node,str(script),str(output)])],check=True,capture_output=True)
            try:
                owned(['tmux','set-option','-t','proxy-test','status','off'],check=True,capture_output=True)
                path=root/'session.json';path.write_text('{}')
                row={'kind':'run','run_dir':tmp,'run_id':'fixture::agent','agent':'claude',
                     'alive':True,'busy':False,'tmux_session':'proxy-test'}
                row.update(proxy_delivery.save(row,'devin'))
                with patch.object(dashboard.subprocess,'run',side_effect=owned):
                    service=proxy_delivery.ProxyDelivery(lambda:[row],dashboard._proxy_ready_screen,dashboard._send_proxy_instruction,lambda:None)
                    for _ in range(30):
                        capture=owned(['tmux','capture-pane','-p','-t','proxy-test'],capture_output=True,text=True).stdout
                        if 'keep draft' in capture: break
                        time.sleep(.05)
                    service.tick([row]);service.tick([row])
                    self.assertFalse(output.exists(),'A native draft is never submitted')
                    before=owned(['tmux','display-message','-p','-t','proxy-test','#{pane_pid}'],capture_output=True,text=True).stdout
                    owned(['tmux','send-keys','-t','proxy-test','C-u'],check=True,capture_output=True)
                    for _ in range(30):
                        if dashboard._proxy_ready_screen(row): break
                        time.sleep(.05)
                    self.assertTrue(dashboard._proxy_ready_screen(row),'Fixture editor is ready')
                    service.tick([row]);time.sleep(2.05);service.tick([row])
                    for _ in range(30):
                        if output.exists(): break
                        time.sleep(.05)
                    self.assertTrue(output.exists(),'The queued instruction reached the actual PTY')
                    message=json.loads(output.read_text())
                    self.assertTrue(message.startswith('\x1b[200~[SiLing'))
                    self.assertIn('Remote proxy mode: devin',message)
                    self.assertNotIn('keep draft',message)
                    self.assertTrue(message.endswith('\x1b[201~\r'))
                    self.assertEqual(json.loads(path.read_text())['proxy_delivery_status'],'sent')
                    after=owned(['tmux','display-message','-p','-t','proxy-test','#{pane_pid}'],capture_output=True,text=True).stdout
                    self.assertEqual(before,after,'The process was not restarted')
            finally:
                owned(['tmux','kill-server'],capture_output=True)
