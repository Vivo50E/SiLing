"""Durable, at-most-once live delivery of pane execution preferences."""
from __future__ import annotations

import re
import json
import threading
import time
import uuid
from pathlib import Path

from .json_store import edit_json
from .proxy_mode import instructions


def metadata_path(row: dict) -> Path:
    return Path(row['run_dir']) / ('session.json' if row['kind'] == 'run' else 'state.json')


def record(data: dict, row: dict) -> dict:
    return data if row['kind'] == 'run' else data[row['task']]


def save(row: dict, mode: str) -> dict:
    with edit_json(metadata_path(row)) as data:
        target = record(data, row)
        # Duplicate HTTP requests must not submit the same instruction twice.
        if target.get('proxy_mode') != mode or not target.get('proxy_delivery_status'):
            target.update(proxy_mode=mode, proxy_delivery_status='queued',
                          proxy_delivery_revision=uuid.uuid4().hex)
        return {key: target.get(key, '') for key in (
            'proxy_mode', 'proxy_mode_applied', 'proxy_delivery_status')}


def empty_editor(screen: str, x: int, y: int) -> bool:
    """Require the live cursor at an empty editor, not an old prompt in history.

    Known placeholders count only when dim-styled and the cursor is at their
    start. Unknown layouts stay pending rather than submitting somebody's draft.
    """
    lines = screen.splitlines()
    if y < 0 or y >= len(lines):
        return False
    strip = lambda line: re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line)
    raw = lines[y]
    line = strip(raw)
    match = re.fullmatch(r'(\s*(?:│\s*)?[❯›>→] ?)(.*?)(?:\s*│)?', line)
    if not match or not len(match[1].rstrip()) <= x <= len(match[1]) + 1:
        return False
    content = match[2].strip()
    dim = any('2' in style.split(';') for style in re.findall(r'\x1b\[([0-9;]*)m', raw))
    if content and not (dim and content in (
        'Ask Claude to do anything', 'Ask Codex to do anything',
        'Write tests for @filename', 'Type a message', 'Type your message',
        'Plan, search, build anything', 'Add a follow-up',
    )):
        return False
    # A multiline draft with its cursor on an empty first line is not empty.
    for following in lines[y + 1:]:
        clean = strip(following).strip().strip('│').strip()
        if not clean or re.fullmatch(r'[─━╭╮╰╯┌┐└┘┴┬├┤┼\s]+', clean):
            continue
        return bool(re.search(r'mode on|for shortcuts|for commands|context left|shift\+tab|·', clean, re.I))
    return False


class ProxyDelivery:
    def __init__(self, rows, probe, send, refresh):
        self.rows, self.probe, self.send, self.refresh = rows, probe, send, refresh
        self.stop_event = threading.Event()
        self.thread = None
        self.stable = {}

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True, name='siling-proxy-delivery')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def run(self):
        while not self.stop_event.wait(2):
            try:
                self.tick(self.rows())
            except (OSError, ValueError, KeyError, TypeError):
                # Inventory/read failures are not evidence of readiness.
                self.stable.clear()

    def tick(self, rows):
        observed = set()
        for row in rows:
            if self.stop_event.is_set():
                return
            if (row.get('remote') or row.get('kind') not in ('run', 'task')
                    or row.get('proxy_delivery_status') != 'queued'
                    or not row.get('proxy_mode') or not row.get('alive')
                    or row.get('agent_exited') or row.get('busy') is not False
                    or row.get('background_active') or row.get('detached_shell_running')
                    or row.get('agent') not in ('claude', 'codex', 'cursor', 'agent')):
                continue
            key = row['run_id']
            observed.add(key)
            try:
                self.deliver(row, key)
            except (OSError, ValueError, KeyError, TypeError):
                self.stable.pop(key, None)
        self.stable = {key: value for key, value in self.stable.items() if key in observed}

    def deliver(self, row, key):
        path = metadata_path(row)
        # Writers replace atomically; polling must not rewrite session metadata.
        target = record(json.loads(path.read_text()), row)
        if target.get('proxy_delivery_status') != 'queued':
            self.stable.pop(key, None)
            return
        revision, mode = target['proxy_delivery_revision'], target['proxy_mode']
        ready = self.probe(row)
        identity = (revision, row.get('tmux_session'), ready)
        previous = self.stable.get(key)
        if not ready:
            self.stable.pop(key, None)
            return
        if not previous or previous[0] != identity:
            self.stable[key] = (identity, time.monotonic())
            return
        if time.monotonic() - previous[1] < 2:
            return
        with edit_json(path) as data:
            target = record(data, row)
            if target.get('proxy_delivery_revision') != revision or target.get('proxy_delivery_status') != 'queued':
                return
            # Journal BEFORE input. A crash/timeout must not replay a paid task.
            target['proxy_delivery_status'] = 'sending'
        status = 'uncertain'
        try:
            if self.stop_event.is_set() or self.probe(row) != ready:
                status = 'queued'
            elif self.send(row, instructions(mode)):
                status = 'sent'
        except Exception:
            # A transport exception may occur after the input reached the CLI.
            pass
        finally:
            with edit_json(path) as data:
                target = record(data, row)
                same_revision = target.get('proxy_delivery_revision') == revision
                if status == 'sent' and (same_revision or target.get('proxy_delivery_status') == 'queued'):
                    target['proxy_mode_applied'] = mode
                if same_revision:
                    target['proxy_delivery_status'] = status
            self.stable.pop(key, None)
            self.refresh()
