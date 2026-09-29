"""Host browser opening, restricted to direct requests from this Mac."""

import ipaddress
import subprocess
import sys
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def system_browser_available(request: Request) -> bool:
    if sys.platform != "darwin" or request.client is None:
        return False
    # Never infer locality from Host, User-Agent or forwarded client headers.
    # Proxies/tunnels must keep opening on the viewing device instead.
    if any(name == "forwarded" or name.startswith("x-forwarded-")
           for name in request.headers):
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
        peer = getattr(peer, "ipv4_mapped", None) or peer
        if peer.is_loopback:
            return True
        server = request.scope.get("server")
        local = ipaddress.ip_address(server[0]) if server else None
        local = getattr(local, "ipv4_mapped", None) or local
        return bool(local and not local.is_unspecified and peer == local)
    except ValueError:
        return False


def validate_web_url(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 16384:
        raise HTTPException(400, "HTTP(S) URL required")
    if any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
        raise HTTPException(400, "invalid URL characters")
    try:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None):
            raise ValueError
        _ = parts.port
    except ValueError as exc:
        raise HTTPException(400, "HTTP(S) URL without credentials required") from exc
    return value


def open_system_browser(url: str) -> None:
    # LaunchServices, like NSWorkspace.open: no Edge/PWA profile is supplied.
    # Do not interpolate a shell command or log possibly sensitive URL queries.
    try:
        result = subprocess.run(
            ["/usr/bin/open", url], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "system open timed out; check the browser before retrying") from exc
    except OSError as exc:
        raise HTTPException(503, "system browser could not be started") from exc
    if result.returncode:
        raise HTTPException(502, "macOS could not open the link")
