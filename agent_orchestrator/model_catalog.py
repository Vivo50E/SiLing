"""Read CLI model catalogs without starting a conversation or inference turn."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import signal
import time


QUERY_TIMEOUT = 15


class CatalogUnavailable(Exception):
    pass


def executable(agent: str) -> str:
    names = {"cursor": ("agent", "cursor-agent"), "claude": ("claude",), "codex": ("codex",)}[agent]
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        candidate = Path.home() / ".local/bin" / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise CatalogUnavailable("Agent CLI is not installed on this node")


def normalize(rows: list, agent: str) -> list[dict]:
    if not isinstance(rows, list):
        raise CatalogUnavailable("Invalid CLI model catalog")
    models = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("hidden"):
            continue
        value = row.get("value") if agent == "claude" else row.get("model", row.get("id"))
        if (not isinstance(value, str) or not value or len(value) > 240
                or any(ord(c) < 32 for c in value) or value in seen):
            continue
        seen.add(value)
        label = row.get("displayName", row.get("label", value))
        models.append({"id": value, "label": str(label)[:240]})
        if len(models) == 200:
            break
    if not models:
        raise CatalogUnavailable("CLI returned no selectable models; use a custom model")
    return models


async def discover(agent: str, cwd: str) -> list[dict]:
    binary = executable(agent)
    if agent == "cursor":
        args = [binary, "--list-models"]
    elif agent == "claude":
        args = [binary, "--print", "--input-format", "stream-json", "--output-format", "stream-json",
                "--verbose", "--no-session-persistence", "--tools", "", "--strict-mcp-config",
                "--mcp-config", '{"mcpServers":{}}', "--settings", '{"disableAllHooks":true}']
    else:
        args = [binary, "app-server"]
    process = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True, limit=1024 * 1024,
    )

    async def send(message):
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()

    async def read_catalog():
        if agent == "claude":
            await send({"type": "control_request", "request_id": "models", "request": {"subtype": "initialize"}})
        elif agent == "codex":
            await send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "siling_model_picker", "version": "1"}}})
        total = 0
        cursor_rows = []
        while True:
            line = await process.stdout.readline()
            total += len(line)
            if total > 1024 * 1024:
                raise CatalogUnavailable("CLI model response is too large")
            if not line:
                if agent == "cursor" and await process.wait() == 0:
                    return normalize(cursor_rows, agent)
                raise CatalogUnavailable("CLI model query failed; use a custom model")
            if agent == "cursor":
                text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line.decode(errors="replace")).strip()
                match = re.fullmatch(r"([\w.:-]+)\s+-\s+(.+)", text)
                if match:
                    cursor_rows.append({"model": match[1], "label": match[2]})
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            if agent == "claude" and data.get("type") == "control_response":
                response = data.get("response", {})
                if response.get("request_id") == "models":
                    return normalize(response.get("response", {}).get("models", []), agent)
            elif agent == "codex" and data.get("id") == 1:
                if "error" in data:
                    raise CatalogUnavailable("Codex model query initialization failed")
                await send({"method": "initialized"})
                await send({"id": 2, "method": "model/list", "params": {"limit": 200}})
            elif agent == "codex" and data.get("id") == 2:
                return normalize(data.get("result", {}).get("data", []), agent)
    try:
        return await asyncio.wait_for(read_catalog(), timeout=QUERY_TIMEOUT)
    except (TimeoutError, OSError, ValueError, TypeError, AttributeError) as exc:
        raise CatalogUnavailable("CLI model query unavailable; retry or use a custom model") from exc
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        process.stdin.close()


class ModelCatalog:
    def __init__(self):
        self.cache = {}
        self.lock = asyncio.Lock()

    async def query(self, agent: str, cwd: str, refresh: bool = False) -> dict:
        key = (agent, cwd)
        async with self.lock:
            cached = self.cache.get(key)
            if not refresh and cached and time.monotonic() - cached[0] < 300:
                return cached[1]
            try:
                result = {"models": await discover(agent, cwd), "error": ""}
            except (CatalogUnavailable, OSError) as exc:
                result = {"models": [], "error": str(exc) if isinstance(exc, CatalogUnavailable) else "Unable to start agent CLI"}
            if len(self.cache) >= 64:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (time.monotonic(), result)
            return result
