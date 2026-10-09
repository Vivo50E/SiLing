"""Legacy terminal secret input is disabled; protected transport checks remain."""
from __future__ import annotations

import ipaddress

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
    """Retired: terminal input can become an agent message or shell history."""
    return False
