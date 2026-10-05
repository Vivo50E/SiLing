"""Cursor redraw transport, independent of model access or vendor installation."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CursorSyncOutputTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required')
    def test_atomic_writes_and_invocation_scope(self):
        subprocess.run(['node', 'tests/cursor_sync_output.cjs'], cwd=ROOT, check=True,
                       capture_output=True, text=True, timeout=15)

    @unittest.skipUnless(shutil.which('node') and shutil.which('tmux'), 'Node.js and tmux required')
    def test_large_replay_is_atomic_through_real_tmux(self):
        import fcntl
        import os
        import pty
        import re
        import select
        import shlex
        import struct
        import tempfile
        import termios
        import time
        version = subprocess.check_output(['tmux', '-V'], text=True)
        match = re.search(r'(\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (3, 7):
            self.skipTest('tmux 3.7+ is required for application synchronized output')
        with tempfile.TemporaryDirectory(prefix='siling-redraw-', dir='/tmp') as folder:
            base = Path(folder)
            socket = str(base / 'tmux.sock')
            fixture = base / 'writer.cjs'
            fixture.write_text("const fs=require('fs');const timer=setInterval(()=>{if(!fs.existsSync(process.argv[2]))return;clearInterval(timer);let data='\\x1b[2J\\x1b[3J\\x1b[H';for(let i=0;i<150000;i++)data+='REPLAY-'+i+'-abcdefghijklmnopqrstuvwxyz\\n';data+='FINAL-STABLE-FRAME\\n';process.stdout.write(data);},20);setInterval(()=>{},10000);")
            def tm(*args):
                return subprocess.check_output(['tmux', '-S', socket, *args], stderr=subprocess.DEVNULL)
            outputs, screens = {}, {}
            try:
                for mode in ('plain', 'sync'):
                    trigger = base / mode
                    argv = [shutil.which('node'), str(fixture), str(trigger)]
                    if mode == 'sync':
                        hook = ROOT / 'scripts/cursor-sync-output.cjs'
                        argv = ['env', 'SILING_CURSOR_SYNC_ONCE=1', f'NODE_OPTIONS= --require="{hook}"', *argv]
                    tm('-f', '/dev/null', 'new-session', '-d', '-s', mode, '-x', '35', '-y', '10', shlex.join(argv))
                    tm('set-option', '-t', mode, 'status', 'off')
                    master, slave = pty.openpty()
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 10, 35, 0, 0))
                    client = subprocess.Popen(['tmux', '-S', socket, 'attach', '-t', mode],
                                              stdin=slave, stdout=slave, stderr=slave,
                                              env={**os.environ, 'TERM':'xterm-256color'})
                    os.close(slave)
                    try:
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline:
                            if tm('list-clients', '-t', mode).strip():
                                break
                            time.sleep(.02)
                        trigger.touch()
                        data = bytearray()
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            if select.select([master], [], [], .1)[0]:
                                data.extend(os.read(master, 65536))
                            if b'FINAL-STABLE-FRAME' in data:
                                break
                        self.assertIn(b'FINAL-STABLE-FRAME', data, mode)
                        outputs[mode] = bytes(data)
                        screens[mode] = tm('capture-pane', '-p', '-t', mode)
                        history = tm('capture-pane', '-p', '-S', '-30', '-t', mode)
                        self.assertIn(b'REPLAY-149990', history, 'History remains available for copying')
                    finally:
                        tm('kill-session', '-t', mode)
                        client.wait(timeout=5)
                        os.close(master)
                self.assertEqual(screens['plain'], screens['sync'], 'Atomic transport preserves the final screen')
                self.assertLessEqual(outputs['sync'].count(b'REPLAY-'), 10, 'Only the final viewport may be shown')
                self.assertGreater(outputs['plain'].count(b'REPLAY-'), 100, 'Unpatched transport reproduces partial replay')
            finally:
                subprocess.run(['tmux', '-S', socket, 'kill-server'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
