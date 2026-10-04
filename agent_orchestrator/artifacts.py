"""Versioned artifact identity/provenance inside existing Linked Items records."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

FIELDS = ('source_run_id', 'source_task', 'execution_id', 'host', 'source_path',
          'description', 'discovery', 'verified_at', 'purpose')


def metadata(record: dict, run: dict | None = None, **updates) -> dict:
    run = run or {}
    old = record.get('artifact') if isinstance(record.get('artifact'), dict) else {}
    result = {key: str(old.get(key) or '')[:8192] for key in FIELDS}
    result.update({key: str(value)[:8192] for key, value in updates.items() if key in FIELDS and value is not None})
    result['host'] = result['host'] or 'local'
    result['source_path'] = result['source_path'] or str(record.get('path') or '')
    result['source_run_id'] = result['source_run_id'] or str(run.get('run_id') or '')
    result['source_task'] = result['source_task'] or str(run.get('task') or '')
    result['execution_id'] = result['execution_id'] or result['source_run_id']
    result['discovery'] = result['discovery'] or 'legacy'
    if result['purpose'] not in ('reference', 'deliverable'):
        result['purpose'] = 'reference'
    identity = [result['host'], result['source_path'], record.get('type') or 'folder']
    result['id'] = 'artifact-' + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:32]
    result['schema_version'] = 1
    return result


def stamp(container: dict, path: str, run: dict, **updates) -> None:
    for record in container.get('linked_folders', []):
        if isinstance(record, dict) and record.get('path') == path:
            record['artifact'] = metadata(record, run, **updates)
            if record.get('type') != 'url':
                record['artifact']['verified_at'] = datetime.now(timezone.utc).isoformat()


def describe(summary: dict, run: dict) -> dict:
    result = dict(summary)
    meta = metadata(summary, run)
    result['artifact'] = meta
    result['artifact_id'] = meta['id']
    if summary.get('type') == 'url':
        result['availability'] = 'candidate'  # Valid syntax does not prove reachability.
        result['preview_capability'] = 'external'
    elif not summary.get('exists') or not summary.get('allowed'):
        result['availability'] = 'inaccessible'
        result['preview_capability'] = 'unavailable'
    else:
        result['availability'] = 'verified'
        result['preview_capability'] = ('browse' if summary.get('type') == 'folder' else
            'preview' if any(e.get('previewable') for e in summary.get('entries', [])) else 'download')
    result['snapshot'] = meta['host'] != 'local'
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    return result
