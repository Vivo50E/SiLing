"""Reversible, Dashboard-wide filing of individual persisted execution records."""
from __future__ import annotations

import json
from pathlib import Path
import time

from .json_store import edit_json


class ArchiveConflict(ValueError):
    pass


def validate(data: dict) -> dict:
    if data == {}:
        return {"version": 1, "revision": 0, "entries": {}}
    if (not isinstance(data, dict) or data.get("version") != 1
            or type(data.get("revision")) is not int or data["revision"] < 0
            or not isinstance(data.get("entries"), dict)):
        raise ValueError("Invalid archive storage")
    for key, item in data["entries"].items():
        if (not key or not isinstance(item, dict) or type(item.get("archived")) is not bool
                or type(item.get("revision")) is not int or item["revision"] < 1
                or type(item.get("archived_at")) not in (float, int)
                or not 0 <= item["archived_at"] <= 253402300799):
            raise ValueError("Invalid archive entry")
    return data


class SessionArchives:
    def __init__(self, outputs_dir: Path):
        self.path = outputs_dir / ".session-archives.json"

    def read(self) -> dict:
        try:
            return validate(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return validate({})

    def change(self, run_id: str, archived: bool, expected_revision: int) -> dict:
        if (not isinstance(run_id, str) or not run_id or len(run_id) > 2048
                or type(archived) is not bool or type(expected_revision) is not int
                or expected_revision < 0):
            raise ValueError("Invalid archive request")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with edit_json(self.path, create=True) as raw:
            data = validate(raw)
            previous = data["entries"].get(run_id, {"archived": False, "revision": 0})
            # An immediate duplicate is idempotent, but an intervening unarchive /
            # archive cycle must not make a stale request authoritative again.
            revision = previous["revision"]
            if expected_revision != revision:
                if previous["archived"] != archived or expected_revision != revision - 1:
                    raise ArchiveConflict("Archive state changed; refresh before retrying")
            elif previous["archived"] != archived:
                data["entries"][run_id] = {"archived": archived,
                    "archived_at": time.time() if archived else 0,
                    "revision": revision + 1}
                data["revision"] += 1
            raw.update(data)
        return data
