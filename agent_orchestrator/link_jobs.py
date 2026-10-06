"""Bounded, durable Link workers. Never send input to the source terminal."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

from .json_store import write_json
from .terminal_files import FileLinkError

ACTIVE = {'queued', 'running', 'cancelling'}


class LinkJobs:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.RLock()
        self.slots = threading.Semaphore(2)
        self.jobs = {}
        self.events = {}
        self.gates = {}
        self.threads = set()
        self.owner = None
        self.closed = False

    def _start(self):
        if self.closed:
            raise ValueError('Link worker is shutting down')
        if self.owner:
            return
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        owner = (self.directory / 'owner.lock').open('a')
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            owner.close()
            raise ValueError('Link workers are owned by another Dashboard process') from None
        try:
            path = self.directory / 'jobs.json'
            self.jobs = json.loads(path.read_text()) if path.exists() else {}
            for job in self.jobs.values():
                if job['status'] in ACTIVE:
                    job.update(status='interrupted', error='Dashboard restarted; review existing results before retrying', updated_at=time.time())
            self.owner = owner
            self._save()
        except Exception:
            self.owner = None
            owner.close()
            raise

    def _save(self):
        write_json(self.directory / 'jobs.json', self.jobs)

    def list(self, run_id):
        with self.lock:
            self._start()
            return copy.deepcopy([j for j in reversed(list(self.jobs.values())) if j['run_id'] == run_id][:20])

    def submit(self, run_id, context, text, request_id, extract, register):
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ValueError('Select 1–16000 characters to identify files')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('A request ID of 1–80 characters is required')
        fingerprint = hashlib.sha256(json.dumps([context, text], sort_keys=True).encode()).hexdigest()
        with self.lock:
            self._start()
            for job in self.jobs.values():
                if job['run_id'] != run_id:
                    continue
                if job['request_id'] == request_id:
                    if job['fingerprint'] != fingerprint:
                        raise ValueError('Request ID already used with different input')
                    return copy.deepcopy(job)
                if job['status'] in ACTIVE:
                    return copy.deepcopy(job)  # One active job per source pane.
            if sum(j['status'] in ACTIVE for j in self.jobs.values()) >= 8:
                raise ValueError('Link queue is full; try again later')
            while len(self.jobs) >= 128:
                oldest = next(k for k, j in self.jobs.items() if j['status'] not in ACTIVE)
                del self.jobs[oldest]
                self.gates.pop(oldest, None)
            job_id = uuid.uuid4().hex
            job = dict(id=job_id, run_id=run_id, context=copy.deepcopy(context),
                       request_id=request_id, fingerprint=fingerprint, status='queued',
                       created_at=time.time(), updated_at=time.time(), files=[], errors=[], error='', limited=False)
            self.jobs[job_id] = job
            event = self.events[job_id] = threading.Event()
            self.gates[job_id] = threading.Lock()
            self._save()
            thread = threading.Thread(target=self._run, args=(job_id, text, event, extract, register), daemon=True)
            self.threads.add(thread)
            thread.start()
            return copy.deepcopy(job)

    def _run(self, job_id, text, event, extract, register):
        acquired = False
        try:
            while not event.is_set():
                if self.slots.acquire(timeout=.1):
                    acquired = True
                    break
            if event.is_set():
                return
            with self.lock:
                job = self.jobs[job_id]
                job.update(status='running', updated_at=time.time())
                self._save()
            paths = extract(text, event)
            with self.lock:
                job['limited'] = len(paths) > 8
            for raw in paths[:8]:
                # The per-job gate serializes cancellation with registration. Once
                # cancel returns, no new registration for this job can begin.
                with self.gates[job_id]:
                    if event.is_set():
                        break
                    try:
                        result = register(raw)
                        error = None
                    except Exception as exc:
                        result = None
                        error = {'path': raw, 'error': str(exc) if isinstance(exc, FileLinkError) else 'File could not be verified or linked'}
                    with self.lock:
                        if error:
                            job['errors'].append(error)
                        else:
                            job['files'].append(result)
                        job['updated_at'] = time.time()
                        self._save()
            with self.lock:
                job['status'] = 'cancelled' if event.is_set() else ('failed' if job['errors'] else 'completed')
        except Exception as exc:
            with self.lock:
                job = self.jobs[job_id]
                job['status'] = 'cancelled' if event.is_set() else 'failed'
                # Only controlled validation errors are user-facing; never expose CLI stderr.
                job['error'] = str(exc) if isinstance(exc, ValueError) else 'Link worker failed; check Claude availability and retry'
        finally:
            with self.lock:
                job = self.jobs[job_id]
                if event.is_set():
                    job['status'] = 'cancelled'
                job['updated_at'] = time.time()
                self._save()
                self.events.pop(job_id, None)
                self.threads.discard(threading.current_thread())
                if self.closed and not self.threads and self.owner:
                    self.owner.close()
                    self.owner = None
            if acquired:
                self.slots.release()

    def cancel(self, run_id, job_id):
        with self.lock:
            self._start()
            job = self.jobs.get(job_id)
            if not job or job['run_id'] != run_id:
                raise KeyError(job_id)
            event = self.events.get(job_id)
            gate = self.gates.get(job_id)
            if event:
                event.set()
                job.update(status='cancelling', updated_at=time.time())
                self._save()
        if gate:
            with gate:
                pass  # Let any already-started registration settle before acknowledging.
        with self.lock:
            return copy.deepcopy(job)

    def close(self):
        with self.lock:
            self.closed = True
            for event in self.events.values():
                event.set()
            if not self.threads and self.owner:
                self.owner.close()
                self.owner = None
