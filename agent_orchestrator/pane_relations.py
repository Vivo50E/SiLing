"""Recover pane-switch families from durable receipts, including older releases."""
import json
from pathlib import Path


def annotate(rows: list[dict], path: Path) -> None:
    try:
        receipts = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    if not isinstance(receipts, dict):
        return
    graph: dict[str, set[str]] = {}
    for entry in receipts.values():
        result = entry.get('result') if isinstance(entry, dict) else None
        if not isinstance(result, dict):
            continue
        source, child = result.get('switched_from'), result.get('run_id')
        if not isinstance(source, str) or not isinstance(child, str) or not source or not child:
            continue
        graph.setdefault(source, set()).add(child)
        graph.setdefault(child, set()).add(source)
    groups = {}
    for start in graph:
        if start in groups:
            continue
        visited, queue = set(), [start]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(graph.get(node, ()))
        for node in visited:
            groups[node] = visited
    for row in rows:
        run_id = row.get('run_id')
        if run_id in groups:
            row['related_run_ids'] = sorted(groups[run_id] - {run_id})
