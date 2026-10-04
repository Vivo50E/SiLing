"""Read-only state projection and persisted lineage for explicit resume attempts.

Observations never launch processes. A disconnected remote node has unknown
execution state even if its last native event said that it was working.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .json_store import edit_json


def identity(row: dict) -> dict:
    attempt = str(row.get('run_id') or row.get('source_run_id') or '')
    parent = str(row.get('resumed_from_run_id') or '')
    root = str(row.get('logical_session_id') or '')
    remote_lifecycle = row.get('lifecycle') if row.get('remote') else None
    if isinstance(remote_lifecycle, dict):
        root = str(remote_lifecycle.get('logical_session_id') or root)
    if row.get('remote') and root:
        # The owning Dashboard defines lineage. Namespace its identity instead
        # of deriving a new root from the remotely qualified attempt ID.
        key = f"{row.get('node_id') or 'remote'}:{root}"
        root = 'session-' + hashlib.sha256(key.encode()).hexdigest()[:32]
    elif not root:
        key = f"{row.get('node_id') or 'local'}:{parent or attempt}"
        root = 'session-' + hashlib.sha256(key.encode()).hexdigest()[:32]
    return {'logical_session_id': root, 'execution_id': attempt,
            'previous_execution_id': parent,
            'native_resume_id': str(row.get('resume_id') or '')}


def record_resume(source: dict, spawned: dict) -> str:
    """Save lineage independently of native resume-ID capture (including shells)."""
    raw = spawned.get('run_dir')
    if not raw:
        return 'No run directory; execution lineage could not be saved'
    try:
        with edit_json(Path(raw) / 'session.json') as data:
            data['logical_session_id'] = identity(source)['logical_session_id']
            data['resumed_from_run_id'] = source.get('run_id') or source.get('source_run_id') or ''
        return ''
    except (OSError, ValueError):
        return 'Execution started, but lineage could not be saved'


def project(row: dict, observed_at=None) -> dict:
    native = row.get('native_activity') or {}
    offline = row.get('remote') and row.get('node_online') is False
    alive = bool(row.get('alive'))
    connection = 'offline' if offline else 'available' if alive else 'ended'
    state, source, updated = 'unknown', 'tmux-discovery', observed_at
    if offline:
        source = 'remote-disconnected'
    elif not alive or row.get('agent_exited'):
        state = 'ended'
    elif native.get('state') in {'working', 'background_working', 'waiting_user', 'needs_input', 'ended'}:
        state = native['state']
        source = native.get('source') or 'native-event'
        updated = native.get('updated_at')
    elif row.get('activity_sustained_active') or row.get('busy'):
        state = 'background_working' if row.get('background_active') else 'working'
        source = 'terminal-inferred'
    else:
        state, source = 'ready', 'terminal-inferred'
    if source == 'terminal-inferred' and state == 'working' and row.get('agent') == 'terminal':
        state = 'terminal_active'
    flag = str(row.get('panel_state') or '')
    return {
        **identity(row), 'execution': state, 'connection': connection,
        'priority': flag if flag in {'p0', 'p1', 'p2', 'lead'} else '',
        'manual_flag': flag,
        'attention': 'needs_input' if state == 'needs_input' else 'blocked' if flag == 'blocked' else '',
        'source': source, 'observed_at': updated,
        'inferred': source.startswith('terminal'),
        'recovery': 'reconnect' if offline or alive else
                    'reopen_shell' if row.get('agent') == 'terminal' else
                    'resume' if row.get('resume_id') else 'new_session',
    }
