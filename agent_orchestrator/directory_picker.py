"""Native macOS folder selection; paths are arguments, never AppleScript code."""
import asyncio
from pathlib import Path
import threading

from fastapi import HTTPException

_BUSY = threading.Lock()
_SCRIPT = '''on run argv
    try
        set chosen to choose folder with prompt "Choose a working directory for SiLing" default location (POSIX file (item 1 of argv))
        return POSIX path of chosen
    on error number -128
        return ""
    end try
end run'''


async def choose_directory(value: object) -> str | None:
    if (not isinstance(value, str) or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise HTTPException(400, "Invalid starting directory")
    try:
        start = Path(value).expanduser() if value else Path.home()
    except RuntimeError:
        raise HTTPException(400, "Invalid starting directory") from None
    if not start.is_absolute():
        start = Path.home()
    try:
        while not start.is_dir() and start != start.parent:
            start = start.parent
        start = start.resolve()
    except (OSError, RuntimeError):
        start = Path.home()
    if not _BUSY.acquire(blocking=False):
        raise HTTPException(409, "A folder chooser is already open on this Mac")
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            '/usr/bin/osascript', '-e', _SCRIPT, str(start),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        raw, _ = await asyncio.wait_for(process.communicate(), timeout=180)
        if process.returncode:
            raise HTTPException(503, "Folder chooser unavailable; enter the path manually")
        selected = raw.decode('utf-8').removesuffix('\n')
        if not selected:
            return None
        if len(selected) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in selected):
            raise ValueError
        path = Path(selected)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError
        return str(path.resolve())
    except asyncio.TimeoutError:
        raise HTTPException(504, "Folder selection timed out; enter the path or try again") from None
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(503, "Folder chooser unavailable; enter the path manually") from None
    finally:
        try:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
        finally:
            _BUSY.release()
