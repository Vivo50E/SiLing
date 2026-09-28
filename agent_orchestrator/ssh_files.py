"""Fetch bounded, read-only preview snapshots using the user's SSH configuration."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile

MAX_FILE_BYTES = 16 * 1024 * 1024
# Send the path as a quoted argv value, never executable shell text. O_NONBLOCK
# prevents opening a FIFO from hanging before we can reject non-regular files.
REMOTE_READER = '''import os, stat, sys
fd = os.open(sys.argv[1], os.O_RDONLY | os.O_NONBLOCK)
with os.fdopen(fd, "rb") as f:
    info = os.fstat(f.fileno())
    if not stat.S_ISREG(info.st_mode):
        sys.exit("Only regular files can be previewed")
    limit = int(sys.argv[2])
    if info.st_size > limit:
        sys.exit("File exceeds the 16 MiB preview limit")
    data = f.read(limit + 1)
    if len(data) > limit:
        sys.exit("File exceeds the 16 MiB preview limit")
    sys.stdout.buffer.write(data)
'''


def validate_target(host: str, path: str) -> None:
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]{0,254}", host):
        raise ValueError("Enter an SSH host alias or user@hostname, without ssh options")
    if (not isinstance(path, str) or not path.startswith("/")
            or path.startswith("//") or len(path) > 8192
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or PurePosixPath(path).name in {"", ".", ".."}):
        raise ValueError("An absolute remote file path is required")


def fetch_preview(host: str, path: str, cache_root: Path) -> Path:
    validate_target(host, path)
    command = shlex.join(["python3", "-c", REMOTE_READER, path, str(MAX_FILE_BYTES)])
    argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=yes", "-o", "ClearAllForwardings=yes",
            "-o", "ForwardAgent=no", host, command]
    # A file sink also bounds local memory if remote shell startup prints noise.
    cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256((host + "\0" + path).encode()).hexdigest()
    destination = cache_root / key / PurePosixPath(path).name
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent) as output:
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=subprocess.PIPE, timeout=25, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("SSH preview timed out; check the host and connection") from exc
        except OSError as exc:
            raise ValueError("Unable to start the local SSH client") from exc
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace")[-1000:].strip()
            raise ValueError("SSH preview failed: " + detail)
        if output.tell() > MAX_FILE_BYTES:
            raise ValueError("File exceeds the 16 MiB preview limit")
        # Replace only after a complete successful transfer. Existing snapshots
        # remain readable when a refresh fails; never touch the remote file.
        temporary = Path(output.name)
        os.chmod(temporary, 0o600)
        # Keep NamedTemporaryFile's name alive for portable context cleanup.
        saved_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as saved:
                saved_path = Path(saved.name)
                output.seek(0)
                shutil.copyfileobj(output, saved)
            os.replace(saved_path, destination)
        finally:
            if saved_path is not None:
                saved_path.unlink(missing_ok=True)
    return destination
