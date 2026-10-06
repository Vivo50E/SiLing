"""Volatile credentials for immutable, status-only HTTPS operations.

The agent can reference an operation, never obtain a credential or change its
destination. This is an API boundary on a trusted host, not a same-user sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import http.client
import re
import ssl
import threading
import time
from urllib.parse import unquote, urlsplit


@dataclass(repr=False)
class Operation:
    name: str
    url: str
    method: str
    auth: str
    body: bytes
    value: bytearray
    expires_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)
    revoked: bool = False

    def metadata(self):
        return {'name': self.name, 'url': self.url, 'method': self.method,
                'auth': self.auth, 'expires_at': self.expires_at}

    def erase(self):
        self.revoked = True
        self.value[:] = b'\0' * len(self.value)


class SecretBroker:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.operations = {}
        self.closed = False
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        def expire():
            while not self.stop.wait(1):
                with self.lock:
                    self._prune()
        with self.lock:
            if self.thread is None and not self.closed:
                self.thread = threading.Thread(target=expire, name='siling-secret-expiry', daemon=True)
                self.thread.start()

    def _prune(self):
        for key, operation in list(self.operations.items()):
            if operation.expires_at <= self.clock():
                self.operations.pop(key)
                operation.revoked = True
                # An already-started request may finish; never erase its
                # credential while it is constructing its authentication header.
                if operation.lock.acquire(blocking=False):
                    try:
                        operation.erase()
                    finally:
                        operation.lock.release()

    def register(self, run_id: str, spec: dict):
        if not isinstance(spec, dict) or set(spec) - {'name','url','method','auth','body','value','ttl'}:
            raise ValueError('Invalid secret operation settings')
        name, url, value = (spec.get(key) for key in ('name','url','value'))
        method, auth, body, ttl = (spec.get('method','GET'), spec.get('auth','bearer'),
                                   spec.get('body',''), spec.get('ttl',900))
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name):
            raise ValueError('Use a secret name of 1–64 letters, digits, underscores or hyphens')
        if not isinstance(value, str) or not 8 <= len(value) <= 4096 or any(not 33 <= ord(c) <= 126 for c in value):
            raise ValueError('Use an API key of 8–4096 printable ASCII characters without spaces')
        if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
            raise ValueError('Enter a valid HTTPS URL')
        try:
            target = urlsplit(url)
            valid = (target.scheme == 'https' and target.hostname and not target.username
                     and not target.password and not target.query and not target.fragment
                     and not target.netloc.endswith(':') and target.port != 0)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Use HTTPS without URL credentials, query parameters or fragments')
        if method not in ('GET','POST') or auth not in ('bearer','api-key'):
            raise ValueError('Choose GET or POST and Bearer or X-API-Key authentication')
        if not isinstance(body, str) or len(body.encode('utf-8')) > 4096 or (method == 'GET' and body):
            raise ValueError('Only POST accepts a fixed body, up to 4096 bytes')
        if type(ttl) is not int or not 60 <= ttl <= 3600:
            raise ValueError('Secret lifetime must be 60–3600 seconds')
        if any(value in unquote(text) for text in (name,url,body)):
            raise ValueError('Keep the key only in the private value field')
        operation = Operation(name,url,method,auth,body.encode('utf-8'),bytearray(value.encode('ascii')),self.clock()+ttl)
        with self.lock:
            self._prune()
            if self.closed:
                operation.erase()
                raise ValueError('Secret broker is shutting down')
            if (run_id,name) in self.operations:
                operation.erase()
                raise ValueError('Name already exists; revoke it and enter the key again to change its operation')
            if len(self.operations) >= 64:
                operation.erase()
                raise ValueError('Secret operation limit reached; revoke unused entries')
            self.operations[run_id,name] = operation
        return operation.metadata()

    def list(self, run_id: str):
        with self.lock:
            self._prune()
            return [op.metadata() for (owner,_),op in self.operations.items() if owner == run_id]

    def revoke(self, run_id: str, name: str):
        with self.lock:
            operation = self.operations.pop((run_id,name),None)
            if operation:
                operation.revoked = True
        if operation:
            with operation.lock:
                operation.erase()

    def revoke_run(self, run_id: str):
        with self.lock:
            keys = [name for owner,name in self.operations if owner == run_id]
        for name in keys:
            self.revoke(run_id,name)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        with self.lock:
            self.closed = True
            keys = list(self.operations)
        for owner,name in keys:
            self.revoke(owner,name)

    def call(self, run_id: str, name: str):
        with self.lock:
            self._prune()
            operation = self.operations.get((run_id,name))
        if not operation:
            raise ValueError('Secret operation is missing, expired or revoked')
        if not operation.lock.acquire(blocking=False):
            raise ValueError('Operation is already running; do not retry until its result is known')
        connection = None
        try:
            if operation.revoked or operation.expires_at <= self.clock():
                raise ValueError('Secret operation is missing, expired or revoked')
            target = urlsplit(operation.url)
            # Standard TLS verification, no environment proxies, redirects,
            # request tracing, raw response bodies, response headers or retries.
            connection = http.client.HTTPSConnection(target.hostname, target.port or 443,
                                                      timeout=15, context=ssl.create_default_context())
            key = operation.value.decode('ascii')
            header, credential = ('Authorization','Bearer '+key) if operation.auth == 'bearer' else ('X-API-Key',key)
            connection.request(operation.method, target.path or '/', body=operation.body or None,
                               headers={header:credential,'Content-Type':'application/json','Accept':'application/json'})
            response = connection.getresponse()
            # Never read or forward the body or headers, even on error. A
            # remote API can echo credentials in either, including redirects.
            return {'name':operation.name,'http_status':response.status,
                    'ok':200 <= response.status < 300,'response_body_withheld':True}
        except Exception:
            raise ValueError('Operation failed or delivery is uncertain; check the service before retrying') from None
        finally:
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass
            if operation.revoked or operation.expires_at <= self.clock():
                operation.erase()
            operation.lock.release()
