"""One-shot private input delivery; never put the value in argv or a file."""
from __future__ import annotations

import ipaddress
import subprocess
import uuid

MAX_SECRET_BYTES = 4096


def trusted_transport(scheme: str, peer: str) -> bool:
    if scheme == 'https':
        return True
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


def validate(value: bytes) -> None:
    if not value or len(value) > MAX_SECRET_BYTES:
        raise ValueError('Enter 1–4096 bytes of private input')
    try:
        text = value.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('Private input must be UTF-8 text') from None
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError('Private input must be a single line without control characters')


def send(pane: str, value: bytes, enter: bool) -> bool:
    """Paste once through a named, deleted tmux buffer. Never retry delivery.

    Receiving programs can still echo/store input; this protects our transport,
    not the behavior of arbitrary shells, SSH hosts, or agent applications.
    """
    validate(value)
    if not pane.startswith('%') or not pane[1:].isdigit():
        return False
    name = 'siling-private-' + uuid.uuid4().hex
    try:
        loaded = subprocess.run(
            ['tmux', 'load-buffer', '-b', name, '-'],
            input=value + (b'\r' if enter else b''), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
        if loaded.returncode:
            return False
        result = subprocess.run(
            ['tmux', 'paste-buffer', '-d', '-r', '-b', name, '-t', pane],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5, check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        # Also remove a buffer after a failed/uncertain paste. Deletion is safe
        # to repeat; sending the value again after a timeout is not.
        try:
            subprocess.run(['tmux', 'delete-buffer', '-b', name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
