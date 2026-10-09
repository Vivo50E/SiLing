"""Write one literal dotenv value without sending it through an agent or terminal."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
from urllib.parse import urlparse

MAX_REQUEST_BYTES = 16384
MAX_FILE_BYTES = 262144
FAILURE = 'Configuration write could not be confirmed. Check the destination before retrying.'


def same_origin(origin: str, destination: str) -> bool:
    try:
        a, b = urlparse(origin), urlparse(destination)
        def identity(url):
            return url.scheme, url.hostname, url.port or (443 if url.scheme == 'https' else 80)
        return (a.scheme in ('http', 'https') and not a.username and not a.password
                and not a.path and not a.query and not a.fragment and identity(a) == identity(b))
    except ValueError:
        return False


def validate(spec: dict) -> None:
    if not isinstance(spec, dict) or set(spec) != {'directory', 'host', 'name', 'value', 'confirm'}:
        raise ValueError('Invalid configuration fields')
    if spec['confirm'] is not True:
        raise ValueError('Confirm the plaintext file security boundary')
    if not all(isinstance(spec[k], str) for k in ('directory', 'host', 'name', 'value')):
        raise ValueError('Invalid configuration fields')
    directory = spec['directory']
    if (not directory.startswith('/') or len(directory.encode()) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in directory)
            or any(p in ('.', '..', '') for p in directory[1:].split('/'))):
        raise ValueError('Enter an existing absolute directory without symlinks')
    if spec['host'] and not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]{0,254}', spec['host']):
        raise ValueError('Enter an SSH config alias or user@host')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', spec['name']):
        raise ValueError('Enter a valid environment variable name')
    value = spec['value']
    if (not value or len(value.encode()) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value) or '$' in value or '`' in value):
        raise ValueError('Enter one line of up to 4096 bytes without controls, dollar signs or backticks')


def _ignored(directory: str) -> None:
    """Reject tracked or unignored files in a Git worktree."""
    if not any((parent / '.git').exists() for parent in (Path(directory), *Path(directory).parents)):
        return
    env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    argv = ['git', '-c', 'core.fsmonitor=false', '-C', directory]
    def run(*args):
        return subprocess.run(argv + list(args), stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=5, env=env).returncode
    if run('ls-files', '--error-unmatch', '--', 'backend.env') != 1:
        raise ValueError('backend.env must be untracked and Git-ignored')
    if run('check-ignore', '-q', '--', 'backend.env') != 0:
        raise ValueError('backend.env must be untracked and Git-ignored')


def _updated(original: str, name: str, value: str) -> bytes:
    result = []
    found = False
    replacement = name + '=' + json.dumps(value, ensure_ascii=False) + '\n'
    # Conservative single-line dotenv syntax; reject multiline/ambiguous files.
    assignment = re.compile(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)')
    for line in original.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            result.append(line); continue
        match = assignment.fullmatch(line.rstrip('\r\n'))
        if not match:
            raise ValueError('backend.env must contain only single-line dotenv assignments')
        rhs = match[2]
        if rhs.startswith(('"', "'")) and not re.fullmatch(r'''(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')\s*(?:#.*)?''', rhs):
            raise ValueError('Multiline dotenv values are unsupported')
        if match[1] == name:
            if not found:
                result.append(replacement); found = True
        else:
            result.append(line)
    if not found:
        if result and not result[-1].endswith('\n'):
            result[-1] += '\n'
        result.append(replacement)
    return ''.join(result).encode('utf-8')


def write_local(spec: dict) -> None:
    validate(spec)
    directory = spec['directory']
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    temporary = None
    try:
        for part in directory[1:].split('/'):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        parent = os.fstat(fd)
        if parent.st_uid != os.getuid() or parent.st_mode & 0o022:
            raise ValueError('Destination directory must be owned by you and not group/world writable')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _ignored(directory)
        original = ''
        previous = None
        try:
            source = os.open('backend.env', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            source = None
        if source is not None:
            try:
                previous = os.fstat(source)
                if (not stat.S_ISREG(previous.st_mode) or previous.st_uid != os.getuid()
                        or previous.st_nlink != 1 or previous.st_size > MAX_FILE_BYTES):
                    raise ValueError('Unsafe or oversized backend.env')
                with os.fdopen(source, 'rb', closefd=False) as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError('Oversized backend.env')
                original = raw.decode('utf-8')
            finally:
                os.close(source)
        data = _updated(original, spec['name'], spec['value'])
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('Oversized backend.env')
        # Stage outside Git so an exact backend.env ignore rule cannot leave
        # a transient credential file visible to git add -A.
        staging = Path(tempfile.gettempdir()).resolve()
        if any((parent / '.git').exists() for parent in (staging, *staging.parents)):
            staging = Path('/tmp').resolve()
        if staging.stat().st_dev != parent.st_dev:
            raise ValueError('The private staging directory must share the destination filesystem')
        target, temporary = tempfile.mkstemp(prefix='siling-secret-config-', suffix='.env', dir=staging)
        try:
            os.fchmod(target, 0o600)
            with os.fdopen(target, 'wb', closefd=False) as stream:
                stream.write(data); stream.flush(); os.fsync(target)
        finally:
            os.close(target)
        try:
            current = os.stat('backend.env', dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if ((previous is None) != (current is None) or previous is not None and
                (previous.st_dev, previous.st_ino, previous.st_mtime_ns, previous.st_size) !=
                (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size)):
            raise ValueError('Destination changed; inspect it before retrying')
        os.replace(temporary, 'backend.env', dst_dir_fd=fd)
        temporary = None
    finally:
        if temporary:
            os.unlink(temporary)
        os.close(fd)


def write(spec: dict) -> None:
    validate(spec)
    if not spec['host']:
        write_local(spec)
        return
    # Fixed trusted helper; credentials and all user data travel only on stdin.
    helper = Path(__file__).read_text()
    payload = {**spec, 'host':''}
    result = subprocess.run(['ssh', '-T', '-o', 'PermitLocalCommand=no', '-o', 'RemoteCommand=none', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
                             '-o', 'ConnectTimeout=10', '--', spec['host'],
                             'python3 -I -c ' + shlex.quote(helper)],
                            input=json.dumps(payload, ensure_ascii=False).encode(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    if result.returncode:
        raise RuntimeError(FAILURE)


if __name__ == '__main__':
    import sys
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError('Oversized request')
        write_local(json.loads(raw))
    except Exception:
        # Never print exception text, file contents, values or remote stdout.
        sys.exit(1)
