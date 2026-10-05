"""Optional bundled plugins. No third-party code is loaded into the Dashboard."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .json_store import edit_json
from . import speckit_plugin


class Plugins:
    def __init__(self, outputs: Path):
        self.path = outputs / '.plugins.json'

    def status(self, enabled=None):
        if enabled is None:
            try:
                data = json.loads(self.path.read_text())
            except FileNotFoundError:
                data = {}
        else:
            if type(enabled) is not bool:
                raise ValueError('enabled must be a boolean')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with edit_json(self.path, create=True) as data:
                data['spec-kit'] = enabled
        if not isinstance(data, dict):
            raise ValueError('Invalid plugin settings')
        return {'id': 'spec-kit', 'name': 'Spec Kit',
                'enabled': data.get('spec-kit', False) is True}

    def prepare(self, body):
        if not self.status()['enabled']:
            raise ValueError('Enable Spec Kit first')
        return speckit_plugin.prepare(body)

    def launch(self, body, spawn):
        key = body.get('idempotency_key')
        if not isinstance(key, str) or not 1 <= len(key) <= 240:
            raise ValueError('A launch idempotency_key is required')
        prepared = self.prepare(body)
        if body.get('preview_id') != prepared['preview_id']:
            raise ValueError('Project or request changed; review the prompt again')
        receipt_key = hashlib.sha256(key.encode()).hexdigest()
        with edit_json(self.path, create=True) as data:
            if data.get('spec-kit') is not True:
                raise ValueError('Enable Spec Kit first')
            receipts = data.setdefault('launches', {})
            prior = receipts.get(receipt_key)
            if prior:
                if prior['preview_id'] != prepared['preview_id']:
                    raise ValueError('Launch key already used for another request')
                if prior.get('response'):
                    return {**prior['response'], 'replayed': True}
                raise ValueError('Previous launch is uncertain or failed; check Sessions before preparing another launch')
            # Commit intent before creating a process; interrupted launches never silently repeat.
            receipts[receipt_key] = {'preview_id': prepared['preview_id'], 'status': 'starting'}
        result = spawn(prepared['delegation'])
        with edit_json(self.path, create=True) as data:
            data['launches'][receipt_key].update(status='started', response=result)
        return {**result, 'replayed': False}
