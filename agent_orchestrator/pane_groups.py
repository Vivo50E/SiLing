"""Dashboard-local project groups, independent of priorities and terminal slots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid

from .json_store import edit_json


COLORS = ("blue", "teal", "purple", "orange", "pink", "gray")


def _keys(row: dict) -> tuple[str, str]:
    node = str(row.get("node_id") or "local")
    resume = row.get("resume") if isinstance(row.get("resume"), dict) else {}
    native_id = row.get("resume_id") or resume.get("id")
    agent = resume.get("agent") or row.get("agent") or ""

    def key(parts: list) -> str:
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    return (
        key([node, "run", row["run_id"]]),
        key([node, "native", agent, native_id]) if native_id and agent else "",
    )


def _validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Invalid project-group storage")
    if not data:
        return {"version": 1, "groups": {}, "members": {}}
    if (data.get("version") != 1 or not isinstance(data.get("groups"), dict)
            or not isinstance(data.get("members"), dict)):
        raise ValueError("Invalid project-group storage; existing data was not overwritten")
    for group_id, group in data["groups"].items():
        if (not isinstance(group, dict) or group.get("id") != group_id
                or not isinstance(group.get("name"), str)
                or group.get("color") not in COLORS):
            raise ValueError("Invalid project-group storage")
    if any(not isinstance(v, str) for v in data["members"].values()):
        raise ValueError("Invalid project-group membership storage")
    return data


class PaneGroups:
    def __init__(self, outputs_dir: Path):
        self.path = outputs_dir / ".pane-groups.json"

    def read(self) -> dict:
        try:
            return _validate(json.loads(self.path.read_text()))
        except FileNotFoundError:
            return _validate({})

    def view(self, rows: list[dict]) -> dict:
        data = self.read()
        # Native IDs can be discovered after a session was assigned a group.
        # Retain an alias so a later resume/restart follows the conversation.
        missing = []
        for row in rows:
            run, native = _keys(row)
            if native and native not in data["members"] and run in data["members"]:
                missing.append((run, native))
        if missing:
            with edit_json(self.path) as current:
                _validate(current)
                for run, native in missing:
                    if run in current["members"]:
                        current["members"].setdefault(native, current["members"][run])
                data = current
        members = {}
        for row in rows:
            run, native = _keys(row)
            group_id = data["members"].get(native, data["members"].get(run, ""))
            members[row["run_id"]] = group_id if group_id in data["groups"] else ""
        return {"groups": list(data["groups"].values()), "members": members}

    def change(self, body: dict, rows: list[dict] | None = None) -> None:
        action = body.get("action")
        if action not in ("create", "update", "delete", "assign"):
            raise ValueError("Unknown project-group action")
        group_id = body.get("group_id", "")
        if not isinstance(group_id, str):
            raise ValueError("group_id must be a string")
        if action == "create":
            group_id = ""
        if action in ("create", "update"):
            name, color = body.get("name"), body.get("color")
            if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 64
                    or any(ord(c) < 32 for c in name)):
                raise ValueError("Group name must contain 1–64 characters without control characters")
            if color not in COLORS:
                raise ValueError("Unsupported group color")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with edit_json(self.path, create=True) as raw:
            data = _validate(raw)
            groups, members = data["groups"], data["members"]
            if action != "create" and group_id not in groups:
                if action != "assign" or group_id:
                    raise ValueError("Project group no longer exists; refresh and try again")
            if action in ("create", "update"):
                if any(g["name"].casefold() == name.strip().casefold()
                       and gid != group_id for gid, g in groups.items()):
                    raise ValueError("A project group with this name already exists")
                if action == "create":
                    if len(groups) >= 100:
                        raise ValueError("At most 100 project groups are supported")
                    group_id = uuid.uuid4().hex
                groups[group_id] = {"id": group_id, "name": name.strip(), "color": color}
            elif action == "delete":
                del groups[group_id]
                data["members"] = {k: "" if v == group_id else v for k, v in members.items()}
            else:
                for row in rows or []:
                    for key in _keys(row):
                        if key:
                            # Empty values deliberately override old conversation aliases.
                            members[key] = group_id
            raw.update(data)
