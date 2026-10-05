"""Local recovery for an unresponsive foreground SSH connection in a tmux pane."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=3).stdout


def _processes(text: str) -> dict[int, dict]:
    rows = {}
    for line in text.splitlines():
        fields = line.split(None, 11)
        if len(fields) != 12:
            continue
        try:
            pid, parent, group, foreground, uid = map(int, fields[:5])
        except ValueError:
            continue
        rows[pid] = {'pid': pid, 'parent': parent, 'group': group,
                     'foreground': foreground, 'uid': uid, 'tty': fields[5],
                     'started': ' '.join(fields[6:11]), 'command': fields[11]}
    return rows


def _descends(pid: int, root: int, rows: dict[int, dict]) -> bool:
    seen = set()
    while pid in rows and pid not in seen:
        if pid == root:
            return True
        seen.add(pid)
        pid = rows[pid]['parent']
    return False


def inspect_ssh(pane: str) -> dict:
    """Identify only a foreground, same-user SSH descendant of the pane shell.

    Never use displayed terminal text, host labels or a client-supplied PID.
    Command arguments (which may contain credentials) are not collected.
    """
    info = _run(['tmux', 'display-message', '-p', '-t', pane,
                 '#{pane_id}\t#{pane_pid}\t#{pane_tty}\t#{pane_current_command}']).strip().split('\t')
    if len(info) != 4 or not info[1].isdigit() or Path(info[3]).name != 'ssh':
        raise ValueError('No foreground SSH client in this pane')
    pane_id, raw_root, tty, _ = info
    root = int(raw_root)
    rows = _processes(_run(['ps', '-axo', 'pid=,ppid=,pgid=,tpgid=,uid=,tty=,lstart=,comm=']))
    shell = rows.get(root)
    if not shell or shell['tty'] != tty.removeprefix('/dev/'):
        raise ValueError('Could not verify the terminal process')
    candidates = [row for pid, row in rows.items()
                  if pid != root and row['uid'] == os.getuid()
                  and row['tty'] == shell['tty'] and row['foreground'] > 0
                  and row['group'] == row['foreground'] == shell['foreground']
                  and Path(row['command']).name == 'ssh' and _descends(pid, root, rows)]
    if len(candidates) != 1:
        raise ValueError('Cannot isolate one foreground SSH client; no process was stopped')
    candidate = candidates[0]
    identity = {'pane': pane_id, 'root': shell, 'ssh': candidate}
    token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {'token': token, 'pid': candidate['pid'], 'pane': pane_id}


def disconnect_ssh(pane: str, token: str) -> dict:
    current = inspect_ssh(pane)
    if not token or token != current['token']:
        raise ValueError('The foreground process changed; inspect SSH again before disconnecting')
    # SIGTERM is handled locally by OpenSSH, even when its network peer is lost.
    # Signal the verified PID only, never its group, shell, tmux server or helpers.
    os.kill(current['pid'], signal.SIGTERM)
    return {'ok': True, 'status': 'disconnect_requested'}
