"""User-approved, session-scoped command credentials; no credential-read API."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from .keychain import Keychain


class SessionKeychain(Keychain):
    service = 'SiLing.SessionSecrets.v1'


class SessionSecrets:
    def __init__(self, store=SessionKeychain, clock=time.time, alive=None):
        self.store, self.clock, self.alive = store, clock, alive
        self.lock = threading.RLock()
        self.requests, self.values = {}, {}
        self.closed = False
        self.stop = threading.Event()
        self.thread = None

    def start(self) -> None:
        def expire():
            ticks = 0
            while not self.stop.wait(1):
                with self.lock:
                    self._prune()
                    owners = {r['run_id'] for r in self.requests.values()} | {k[0] for k in self.values}
                ticks += 1
                if self.alive and ticks % 5 == 0:
                    for owner in owners:
                        if not self.alive(owner):
                            self.revoke_run(owner)
        self.thread = threading.Thread(target=expire, daemon=True, name='siling-session-secret-expiry')
        self.thread.start()

    @staticmethod
    def _erase(value):
        value[:] = b'\0' * len(value)

    def _prune(self):
        now = self.clock()
        for key, (value, expires) in list(self.values.items()):
            if expires <= now:
                self._erase(value)
                del self.values[key]
        for rid, row in list(self.requests.items()):
            if row['expires_at'] <= now and row['state'] != 'running':
                del self.requests[rid]

    @staticmethod
    def _scope(row):
        return row['run_id'], row['cwd'], row['name']

    def _store(self, row):
        account = hashlib.sha256((row['cwd'] + '\0' + row['name']).encode()).hexdigest()[:32]
        return self.store(account)

    def _metadata(self, row):
        return {key: row[key] for key in ('id', 'run_id', 'name', 'cwd', 'argv', 'reason',
                'state', 'expires_at', 'exit_code', 'timeout')} | {
            'session_value_available': self._scope(row) in self.values,
            'keychain_supported': sys.platform == 'darwin', 'output_withheld': True}

    def request(self, run_id: str, spec: dict) -> dict:
        if not isinstance(spec, dict) or set(spec) - {'name', 'cwd', 'argv', 'reason', 'timeout'}:
            raise ValueError('Invalid command request')
        name, cwd, argv = (spec.get(k) for k in ('name', 'cwd', 'argv'))
        reason, timeout = spec.get('reason', ''), spec.get('timeout', 60)
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name):
            raise ValueError('Use an environment variable name')
        if (not isinstance(cwd, str) or not Path(cwd).is_absolute() or not Path(cwd).is_dir()
                or not isinstance(argv, list) or not 1 <= len(argv) <= 64
                or any(not isinstance(a, str) or '\0' in a or len(a) > 4096 for a in argv)
                or not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file()):
            raise ValueError('Use an existing absolute working directory and executable')
        if not isinstance(reason, str) or len(reason) > 500 or type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError('Use a short reason and a timeout of 1–120 seconds')
        row = dict(id=uuid.uuid4().hex, run_id=run_id, name=name, cwd=str(Path(cwd).resolve()),
                   argv=list(argv), reason=reason, timeout=timeout, state='pending',
                   expires_at=self.clock()+900, exit_code=None)
        with self.lock:
            self._prune()
            if self.closed or len(self.requests) >= 64:
                raise ValueError('Request limit reached or service stopped')
            for existing in self.requests.values():
                if existing['state'] in ('pending', 'running') and all(existing[k] == row[k] for k in
                        ('run_id', 'name', 'cwd', 'argv', 'reason', 'timeout')):
                    return self._metadata(existing)
            self.requests[row['id']] = row
            return self._metadata(row)

    def list(self, run_id: str | None = None) -> list[dict]:
        with self.lock:
            self._prune()
            return [self._metadata(r) for r in self.requests.values() if run_id is None or r['run_id'] == run_id]

    def _get(self, run_id, request_id):
        self._prune()
        row = self.requests.get(request_id)
        if not row or row['run_id'] != run_id:
            raise ValueError('Request missing or expired')
        return row

    @staticmethod
    def _validate_value(value):
        if not isinstance(value, str) or not 1 <= len(value.encode()) <= 16384 or '\0' in value:
            raise ValueError('Enter a nonempty secret up to 16384 bytes')

    def approve(self, run_id: str, request_id: str, spec: dict) -> dict:
        if (not isinstance(spec, dict) or set(spec) - {'value', 'source', 'save'}
                or spec.get('source') not in ('input', 'session', 'keychain')
                or type(spec.get('save', False)) is not bool):
            raise ValueError('Invalid approval')
        with self.lock:
            row = self._get(run_id, request_id)
            if self.closed or row['state'] != 'pending':
                raise ValueError('Request is no longer pending')
            source = spec['source']
            if source == 'input':
                value = spec.get('value')
            elif source == 'session':
                entry = self.values.get(self._scope(row))
                value = entry[0].decode() if entry else None
            else:
                value = (self._store(row).get() or {}).get('value')
            self._validate_value(value)
            if spec.get('save'):
                self._store(row).set({'value': value})
            old = self.values.pop(self._scope(row), None)
            if old:
                self._erase(old[0])
            self.values[self._scope(row)] = (bytearray(value.encode()), self.clock()+3600)
            row['state'] = 'running'
            row['expires_at'] = self.clock()+3600
            worker = threading.Thread(target=self._execute, args=(row, value), daemon=True,
                                      name='siling-secret-command')
            row['worker'] = worker
            worker.start()
            return self._metadata(row)

    def _execute(self, row, value):
        proc = None
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR') if k in os.environ}
        env[row['name']] = value
        value = None
        state, code = 'failed', None
        try:
            with self.lock:
                if self.closed or row['state'] != 'running':
                    return
                proc = subprocess.Popen(row['argv'], cwd=row['cwd'], env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                row['process'] = proc
            env.clear()
            try:
                code = proc.wait(timeout=row['timeout'])
                state = 'completed' if code == 0 else 'failed'
            except subprocess.TimeoutExpired:
                state = 'timed_out'
        except Exception:
            pass  # Never return exception strings or command output containing credentials.
        finally:
            env.clear()
            if proc:
                self._kill(proc)
                proc.wait()
            with self.lock:
                row.pop('process', None)
                if row['state'] == 'running':
                    row['state'], row['exit_code'] = state, code

    @staticmethod
    def _kill(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def cancel(self, run_id: str, request_id: str) -> dict:
        with self.lock:
            row = self._get(run_id, request_id)
            if row['state'] in ('pending', 'running'):
                row['state'] = 'cancelled'
                if row.get('process'):
                    self._kill(row['process'])
            return self._metadata(row)

    def forget(self, run_id: str, request_id: str, saved: bool = False) -> None:
        with self.lock:
            row = self._get(run_id, request_id)
            if saved:
                self._store(row).delete()
            entry = self.values.pop(self._scope(row), None)
            if entry:
                self._erase(entry[0])

    def revoke_run(self, run_id: str) -> None:
        with self.lock:
            for row in list(self.requests.values()):
                if row['run_id'] == run_id:
                    if row.get('process'):
                        self._kill(row['process'])
                    row['state'] = 'cancelled'
                    self.requests.pop(row['id'], None)
            for key in list(self.values):
                if key[0] == run_id:
                    self._erase(self.values.pop(key)[0])

    def close(self) -> None:
        self.stop.set()
        with self.lock:
            self.closed = True
            workers = [r['worker'] for r in self.requests.values() if 'worker' in r]
            for run_id in {r['run_id'] for r in self.requests.values()} | {k[0] for k in self.values}:
                self.revoke_run(run_id)
        for worker in workers:
            worker.join(timeout=3)
        if self.thread:
            self.thread.join(timeout=2)
